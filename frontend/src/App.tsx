import React, { useRef, useState } from "react";
import {
  CartonSpec,
  DetectedItemMeasurement,
  Dimensions3D,
  OrderAnalysisResponse,
  PackingPlan,
  PackingRequest,
  PackingScenarioCard,
  PackingSolutionResponse,
} from "./types/contract";
import { UploadPanel } from "./components/UploadPanel";
import { ExtendedPackableItem } from "./components/ManifestTable";
import { ItemVerificationPanel } from "./components/ItemVerificationPanel";
import { BoxAnchorCarousel } from "./components/BoxAnchorCarousel";
import { ScenarioComparisonGrid } from "./components/ScenarioComparisonGrid";
import { PackingViewer3D } from "./components/PackingViewer3D";
import { CostScorecard } from "./components/CostScorecard";
import { CartonControlBar } from "./components/CartonControlBar";
import { OptiPackClient } from "./api/optipackClient";
import { needsMeasurementReview } from "./utils/review";

export const convertItem = (item: DetectedItemMeasurement): ExtendedPackableItem => {
  const hasRealAiName = Boolean(
    item.display_name &&
      !/^(generic box|packaged product|item|item #\d+.*|detected object)$/i.test(
        item.display_name.trim()
      )
  );

  const isDefaultSafe =
    !hasRealAiName &&
    item.physical_attributes.fragility_source === "default_safe" &&
    item.physical_attributes.orientation_source === "default_unconstrained" &&
    item.physical_attributes.weight_source === "unknown";

  const isAiExtracted =
    item.measurement_provenance.xy_method !== "demo_fixture_not_measured" &&
    item.measurement_provenance.xy_method !== "manual_input" &&
    !isDefaultSafe;

  const materialType =
    item.physical_attributes.material_type ||
    (item.physical_attributes.fragility_class === "high" ? "glass_ceramic" : "rigid_box");

  const weightTier =
    item.physical_attributes.weight_tier ||
    (item.physical_attributes.weight_g && item.physical_attributes.weight_g < 500
      ? "light"
      : item.physical_attributes.weight_g && item.physical_attributes.weight_g > 2000
      ? "heavy"
      : "medium");

  return {
    item_id: item.item_id,
    display_name: item.display_name,
    quantity: item.quantity,
    dimensions_mm: item.dimensions_mm,
    safety_margin_mm: item.uncertainty_mm.safety_margin_mm,
    weight_g: item.physical_attributes.weight_g,
    weight_assumed: item.physical_attributes.weight_source !== "scale_verified",
    fragility_class: item.physical_attributes.fragility_class,
    keep_upright: item.physical_attributes.keep_upright,
    stackable: item.physical_attributes.stackable,
    max_top_load_g: item.physical_attributes.max_top_load_g,
    allowed_rotations: item.allowed_rotations,
    display_color_hex: item.visual_evidence.display_color_hex,
    crop_url: item.visual_evidence.crop_url,
    provenance_source: isAiExtracted ? "AI-Extracted" : "Default-Safe",
    material_type: materialType,
    weight_tier: weightTier,
    uncertainty_info: {
      height_sigma_mm: item.uncertainty_mm.height_sigma_mm,
      requires_user_review: item.measurement_provenance.requires_user_review,
    },
  };
};

/**
 * Fallback synthesis of 4 What-If scenarios if backend returns a single solution
 * without the scenarios array (offline/legacy compatibility guarantee).
 */
const synthesizeFallbackScenarios = (
  primaryPlan: PackingPlan,
  items: ExtendedPackableItem[],
  userBoxes: CartonSpec[]
): PackingScenarioCard[] => {
  const cards: PackingScenarioCard[] = [];
  const carton = primaryPlan.carton;
  const h = carton.internal_dimensions_mm.height_mm;

  // 1. BEST_FIT Scenario
  cards.push({
    scenario_id: "best_fit",
    title: `Best Fit · ${carton.carton_id}`,
    badge_status: "BEST_FIT",
    badge_label: "Best Fit",
    overflow_height_mm: 0,
    original_box_height_mm: h,
    plan: primaryPlan,
    ai_advisor_note: `Optimal fit with lowest shipping cost.`,
  });

  // 2. GREEN Scenario (Snug Fit)
  cards.push({
    scenario_id: "snug_green",
    title: `Snug Fit · ${carton.carton_id}`,
    badge_status: "GREEN",
    badge_label: "Snug Fit",
    overflow_height_mm: 0,
    original_box_height_mm: h,
    plan: primaryPlan,
    ai_advisor_note: `All ${items.length} items fit flush inside.`,
  });

  // 3. YELLOW Scenario (Elastic Bulge)
  const flexItem = items.find((i) => i.material_type === "soft_fabric") || items[0];
  const deltaH = Math.min(Math.max(10, Math.floor(h * 0.1)), 25);
  cards.push({
    scenario_id: "elastic_yellow",
    title: `Lid Flex · ${carton.carton_id}`,
    badge_status: "YELLOW",
    badge_label: `Lid Flex (+${deltaH}mm)`,
    overflow_height_mm: deltaH,
    original_box_height_mm: Math.max(50, h - deltaH),
    top_item_name: flexItem?.display_name || "flexible item",
    plan: primaryPlan,
    ai_advisor_note: `Lid flexes +${deltaH}mm over soft item. Secure with H-tape.`,
  });

  // 4. RED Scenario (Eject 1 Item if multiple items present)
  if (items.length > 1) {
    const bulkyItem = [...items].sort(
      (a, b) =>
        b.dimensions_mm.length_mm * b.dimensions_mm.width_mm * b.dimensions_mm.height_mm -
        a.dimensions_mm.length_mm * a.dimensions_mm.width_mm * a.dimensions_mm.height_mm
    )[0];
    cards.push({
      scenario_id: "eject_red",
      title: `Split Item · ${carton.carton_id}`,
      badge_status: "RED",
      badge_label: "Split Item",
      overflow_height_mm: 0,
      original_box_height_mm: h,
      top_item_name: bulkyItem.display_name,
      ejected_item_ids: [bulkyItem.item_id],
      plan: primaryPlan,
      ai_advisor_note: `Ship [${bulkyItem.display_name}] separately in a mailer bag.`,
    });
  }

  return cards;
};

export const App: React.FC = () => {
  // Wizard state machine: 1 = Capture, 2 = Verify Items, 3 = Choose Box, 4 = 3D Packing
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3 | 4>(1);

  const [analysis, setAnalysis] = useState<OrderAnalysisResponse | null>(null);
  const [packableItems, setPackableItems] = useState<ExtendedPackableItem[]>([]);
  const [solution, setSolution] = useState<PackingSolutionResponse | null>(null);
  const [selectedBoxes, setSelectedBoxes] = useState<CartonSpec[]>([]);
  const [scenarios, setScenarios] = useState<PackingScenarioCard[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<PackingScenarioCard | null>(null);

  const [activePlanIndex, setActivePlanIndex] = useState<number>(1);
  const [applyUncertaintyMargin, setApplyUncertaintyMargin] = useState<boolean>(true);

  const [cartonMode, setCartonMode] = useState<"auto" | "preset" | "custom">("auto");
  const [selectedCartonSku, setSelectedCartonSku] = useState<string>("BOX-M");
  const [customCartonDims, setCustomCartonDims] = useState<Dimensions3D>({
    length_mm: 300,
    width_mm: 220,
    height_mm: 150,
  });

  const [loading, setLoading] = useState<boolean>(false);
  const [packingLoading, setPackingLoading] = useState<boolean>(false);
  const [packingError, setPackingError] = useState<string | null>(null);

  // Ignore late solver responses
  const packingRequestId = useRef(0);

  const invalidatePacking = () => {
    packingRequestId.current += 1;
    setSolution(null);
    setScenarios([]);
    setSelectedScenario(null);
    setPackingLoading(false);
    setPackingError(null);
  };

  const executePacking = async (
    itemsToPack: ExtendedPackableItem[],
    analysisId: string,
    margin: boolean = applyUncertaintyMargin,
    overrideConfig?: Partial<PackingRequest["solver_config"]>
  ) => {
    if (itemsToPack.length === 0) return;
    if (itemsToPack.some(needsMeasurementReview)) {
      invalidatePacking();
      setPackingError("Confirm all flagged dimensions before requesting a packing plan.");
      return;
    }
    const requestId = ++packingRequestId.current;
    setPackingLoading(true);
    setPackingError(null);
    setSolution(null);
    setScenarios([]);
    setSelectedScenario(null);

    const req: PackingRequest = {
      contract_version: "1.0.0",
      analysis_id: analysisId,
      solver_config: {
        mode: "cpsat_with_heuristic_fallback",
        time_limit_ms: 3000,
        apply_uncertainty_margin: margin,
        min_support_ratio: 0.6,
        allow_multi_carton_split: cartonMode === "auto",
        user_selected_boxes: selectedBoxes,
        ...(cartonMode === "preset" ? { target_carton_id: selectedCartonSku } : {}),
        ...(cartonMode === "custom" ? { custom_carton_dimensions: customCartonDims } : {}),
        ...overrideConfig,
      },
      items: itemsToPack,
    };

    try {
      const data = await OptiPackClient.packOrder(req);
      if (requestId === packingRequestId.current) {
        setSolution(data);
        setActivePlanIndex(1);

        // Populate scenarios from backend or fallback synthesis
        let computedScenarios = data.scenarios && data.scenarios.length > 0 ? data.scenarios : [];
        if (computedScenarios.length === 0 && data.primary_plan) {
          computedScenarios = synthesizeFallbackScenarios(
            data.primary_plan,
            itemsToPack,
            overrideConfig?.user_selected_boxes || selectedBoxes
          );
        }
        setScenarios(computedScenarios);
        setSelectedScenario(computedScenarios[0] || null);
      }
    } catch (err) {
      console.error("[App] Packing optimization failed:", err);
      if (requestId === packingRequestId.current) {
        setSolution(null);
        setScenarios([]);
        setSelectedScenario(null);
        setPackingError(err instanceof Error ? err.message : "Packing failed. Please retry.");
      }
    } finally {
      if (requestId === packingRequestId.current) setPackingLoading(false);
    }
  };

  const handleAnalysisLoaded = (
    data: OrderAnalysisResponse,
    precomputedSolution?: PackingSolutionResponse
  ) => {
    invalidatePacking();
    setAnalysis(data);
    const convertedItems: ExtendedPackableItem[] = data.items.map(convertItem);
    setPackableItems(convertedItems);
    setActivePlanIndex(1);

    if (precomputedSolution) {
      setSolution(precomputedSolution);
      let scs =
        precomputedSolution.scenarios && precomputedSolution.scenarios.length > 0
          ? precomputedSolution.scenarios
          : [];
      if (scs.length === 0 && precomputedSolution.primary_plan) {
        scs = synthesizeFallbackScenarios(precomputedSolution.primary_plan, convertedItems, selectedBoxes);
      }
      setScenarios(scs);
      setSelectedScenario(scs[0] || null);
      setCurrentStep(4);
    } else if (convertedItems.length > 0) {
      // Step 2 is mandatory and non-skippable
      setCurrentStep(2);
    } else {
      setSolution(null);
      setCurrentStep(1);
    }
  };

  const handleUpdateItem = (index: number, updated: ExtendedPackableItem) => {
    const current = packableItems[index];
    const affectsGeometry =
      !current ||
      current.quantity !== updated.quantity ||
      current.keep_upright !== updated.keep_upright ||
      current.dimensions_mm.length_mm !== updated.dimensions_mm.length_mm ||
      current.dimensions_mm.width_mm !== updated.dimensions_mm.width_mm ||
      current.dimensions_mm.height_mm !== updated.dimensions_mm.height_mm ||
      JSON.stringify(current.allowed_rotations) !== JSON.stringify(updated.allowed_rotations);

    if (affectsGeometry) {
      invalidatePacking();
    }
    setPackableItems((prev) => {
      const copy = [...prev];
      copy[index] = updated;
      return copy;
    });
  };

  const handleAddItem = () => {
    invalidatePacking();
    const newItemId = `item_${String(packableItems.length + 1).padStart(2, "0")}`;
    const colors = ["#EC4899", "#14B8A6", "#F97316", "#8B5CF6", "#EAB308"];
    const chosenColor = colors[packableItems.length % colors.length];

    const newItem: ExtendedPackableItem = {
      item_id: newItemId,
      display_name: `Manual Item #${packableItems.length + 1}`,
      quantity: 1,
      dimensions_mm: { length_mm: 120, width_mm: 80, height_mm: 50 },
      safety_margin_mm: 5,
      weight_g: 300,
      weight_assumed: false,
      fragility_class: "low",
      keep_upright: false,
      stackable: true,
      max_top_load_g: 3000,
      allowed_rotations: ["LWH", "WLH", "LHW", "HLW", "WHL", "HWL"],
      display_color_hex: chosenColor,
      crop_url: null,
      provenance_source: "Default-Safe",
      material_type: "rigid_box",
      weight_tier: "light",
      uncertainty_info: {
        height_sigma_mm: 2.0,
        requires_user_review: false,
      },
    };

    setPackableItems((prev) => [...prev, newItem]);
  };

  const handleDeleteItem = (index: number) => {
    invalidatePacking();
    setPackableItems((prev) => prev.filter((_, i) => i !== index));
  };

  const handleToggleBoxSelection = (carton: CartonSpec) => {
    setSelectedBoxes((prev) => {
      const exists = prev.some((c) => c.carton_id === carton.carton_id);
      if (exists) {
        return prev.filter((c) => c.carton_id !== carton.carton_id);
      } else {
        return [...prev, carton];
      }
    });
  };

  const handleUpdateBoxSelection = (oldCartonId: string, updated: CartonSpec) => {
    setSelectedBoxes((prev) =>
      prev.map((c) => (c.carton_id === oldCartonId ? updated : c))
    );
  };

  const handleConfirmVerification = () => {
    setPackingError(null);
    setPackableItems((prev) =>
      prev.map((it) => ({
        ...it,
        review_acknowledged: true,
      }))
    );
    setCurrentStep(3);
  };

  const handleProceedToPacking = (chosenBoxes: CartonSpec[]) => {
    setSelectedBoxes(chosenBoxes);
    if (!analysis) return;
    const verifiedItems = packableItems.map((it) => ({
      ...it,
      review_acknowledged: true,
    }));
    setPackableItems(verifiedItems);
    executePacking(verifiedItems, analysis.analysis_id, applyUncertaintyMargin, {
      user_selected_boxes: chosenBoxes,
    });
    setCurrentStep(4);
  };

  const handleReset = () => {
    invalidatePacking();
    setAnalysis(null);
    setPackableItems([]);
    setSolution(null);
    setScenarios([]);
    setSelectedScenario(null);
    setActivePlanIndex(1);
    setCurrentStep(1);
  };

  const handleStepClick = (step: 1 | 2 | 3 | 4) => {
    if (step === 1) setCurrentStep(1);
    else if (step === 2 && packableItems.length > 0) setCurrentStep(2);
    else if (step === 3 && packableItems.length > 0) setCurrentStep(3);
    else if (step === 4 && (solution || scenarios.length > 0)) setCurrentStep(4);
  };

  // Determine active plan for 3D visualization
  let activePlan: PackingPlan | null = null;
  if (selectedScenario?.plan) {
    activePlan = selectedScenario.plan;
  } else if (solution?.primary_plan) {
    if (activePlanIndex === 1) {
      activePlan = solution.primary_plan;
    } else if (
      solution.overflow_plans &&
      solution.overflow_plans.length >= activePlanIndex - 1
    ) {
      activePlan = solution.overflow_plans[activePlanIndex - 2];
    } else {
      activePlan = solution.primary_plan;
    }
  }

  const isYellowBulge = selectedScenario?.badge_status === "YELLOW";
  const originalBoxHeightMm = selectedScenario?.original_box_height_mm;
  const overflowHeightMm = selectedScenario?.overflow_height_mm;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-group">
          <h1>OptiPack</h1>
          <span className="muted">3D Cartonization</span>
        </div>
      </header>

      {/* 4-Step Stepper Breadcrumbs */}
      <nav className="wizard-stepper" aria-label="Workflow Steps">
        <div
          className={`wizard-step ${currentStep === 1 ? "is-active" : "is-done"}`}
          onClick={() => handleStepClick(1)}
          role="button"
          tabIndex={0}
        >
          <span className="step-num">{currentStep > 1 ? "✓" : "1"}</span>
          <span className="step-label">Capture</span>
        </div>
        <div className="wizard-divider" />
        <div
          className={`wizard-step ${
            currentStep === 2 ? "is-active" : currentStep > 2 ? "is-done" : ""
          }`}
          onClick={() => handleStepClick(2)}
          role="button"
          tabIndex={packableItems.length > 0 ? 0 : -1}
        >
          <span className="step-num">{currentStep > 2 ? "✓" : "2"}</span>
          <span className="step-label">Items</span>
        </div>
        <div className="wizard-divider" />
        <div
          className={`wizard-step ${
            currentStep === 3 ? "is-active" : currentStep > 3 ? "is-done" : ""
          }`}
          onClick={() => handleStepClick(3)}
          role="button"
          tabIndex={packableItems.length > 0 ? 0 : -1}
        >
          <span className="step-num">{currentStep > 3 ? "✓" : "3"}</span>
          <span className="step-label">Boxes</span>
        </div>
        <div className="wizard-divider" />
        <div
          className={`wizard-step ${currentStep === 4 ? "is-active" : ""}`}
          onClick={() => handleStepClick(4)}
          role="button"
          tabIndex={solution || scenarios.length > 0 ? 0 : -1}
        >
          <span className="step-num">4</span>
          <span className="step-label">3D Pack</span>
        </div>
      </nav>

      <main className="layout-content">
        {/* STEP 1: Dual Photo Capture & Camera */}
        {currentStep === 1 && (
          <div className="step-page-container">
            <UploadPanel
              onAnalysisLoaded={handleAnalysisLoaded}
              loading={loading}
              setLoading={setLoading}
              analysis={analysis}
              items={packableItems}
              onReset={handleReset}
              aiTelemetry={analysis?.ai_telemetry}
            />
            {packableItems.length > 0 && (
              <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => setCurrentStep(2)}
                >
                  Verify Items ({packableItems.length}) →
                </button>
              </div>
            )}
          </div>
        )}

        {/* STEP 2: Item Verification (Mandatory & Non-skippable) */}
        {currentStep === 2 && (
          <div className="step-page-container">
            <ItemVerificationPanel
              items={packableItems}
              onUpdateItem={handleUpdateItem}
              onAddItem={handleAddItem}
              onDeleteItem={handleDeleteItem}
              onConfirmAll={handleConfirmVerification}
              onRetake={() => setCurrentStep(1)}
              applyUncertaintyMargin={applyUncertaintyMargin}
              setApplyUncertaintyMargin={setApplyUncertaintyMargin}
            />
          </div>
        )}

        {/* STEP 3: Box Anchor Carousel (Visual Benchmark) */}
        {currentStep === 3 && (
          <div className="step-page-container">
            <BoxAnchorCarousel
              items={packableItems}
              selectedBoxes={selectedBoxes}
              onToggleBoxSelection={handleToggleBoxSelection}
              onUpdateBox={handleUpdateBoxSelection}
              onProceedToPacking={handleProceedToPacking}
              onBack={() => setCurrentStep(2)}
            />
          </div>
        )}

        {/* STEP 4: 3D Packing & What-If Scenarios */}
        {currentStep === 4 && (
          <div className="step-page-container">
            {/* Top Action Nav */}
            <div className="step-nav-bar">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setCurrentStep(3)}
              >
                ← Change Box
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleReset}
              >
                New Order
              </button>
            </div>

            {/* Error or Review Banner */}
            {packingError && (
              <section className="panel packing-error" role="alert" style={{ marginBottom: 16 }}>
                <strong>Packing failed</strong>
                <p>{packingError}</p>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={() =>
                    analysis &&
                    executePacking(packableItems, analysis.analysis_id, applyUncertaintyMargin, {
                      user_selected_boxes: selectedBoxes,
                    })
                  }
                  disabled={packingLoading}
                >
                  Retry packing
                </button>
              </section>
            )}

            {/* Loading Spinner */}
            {packingLoading && (
              <section className="panel" style={{ textAlign: "center", padding: "40px 20px" }}>
                <span style={{ fontSize: 32 }}>📦</span>
                <h3 style={{ marginTop: 12 }}>Solving 3D Packing…</h3>
              </section>
            )}

            {/* What-If Scenarios Cards */}
            {!packingLoading && scenarios.length > 0 && (
              <ScenarioComparisonGrid
                scenarios={scenarios}
                selectedScenarioId={selectedScenario?.scenario_id || null}
                onSelectScenario={(sc) => setSelectedScenario(sc)}
              />
            )}

            {/* 3D Visualizer & Scorecard Grid */}
            {!packingLoading && activePlan && (
              <div className="layout" style={{ marginTop: 16 }}>
                <div className="col">
                  <CostScorecard
                    metrics={activePlan.metrics}
                    validation={activePlan.validation}
                    carton={activePlan.carton}
                    candidateComparison={solution?.candidate_carton_comparison}
                    overflowPlans={solution?.overflow_plans}
                    unpackedItemIds={selectedScenario?.ejected_item_ids || solution?.unpacked_item_ids}
                    activePlanIndex={activePlanIndex}
                    onSelectPlan={setActivePlanIndex}
                  />
                  <div style={{ marginTop: 16 }}>
                    <CartonControlBar
                      cartonMode={cartonMode}
                      setCartonMode={(mode) => {
                        setCartonMode(mode);
                        if (analysis) {
                          executePacking(packableItems, analysis.analysis_id, applyUncertaintyMargin, {
                            ...(mode === "preset" ? { target_carton_id: selectedCartonSku } : {}),
                            ...(mode === "custom" ? { custom_carton_dimensions: customCartonDims } : {}),
                          });
                        }
                      }}
                      selectedCartonSku={selectedCartonSku}
                      setSelectedCartonSku={setSelectedCartonSku}
                      customCartonDims={customCartonDims}
                      setCustomCartonDims={setCustomCartonDims}
                      onApply={() =>
                        analysis &&
                        executePacking(packableItems, analysis.analysis_id, applyUncertaintyMargin, {
                          ...(cartonMode === "preset" ? { target_carton_id: selectedCartonSku } : {}),
                          ...(cartonMode === "custom" ? { custom_carton_dimensions: customCartonDims } : {}),
                        })
                      }
                      loading={packingLoading}
                      currentCartonSku={activePlan.carton.carton_id}
                      currentCartonDims={activePlan.carton.internal_dimensions_mm}
                    />
                  </div>
                </div>

                <div className="col">
                  <PackingViewer3D
                    plan={activePlan}
                    isYellowBulge={isYellowBulge}
                    originalBoxHeightMm={originalBoxHeightMm}
                    overflowHeightMm={overflowHeightMm}
                  />
                </div>
              </div>
            )}

            {!packingLoading && !activePlan && !packingError && (
              <section className="panel empty">
                <span className="empty-sub-icon">📦</span>
                <p className="muted">
                  No packing plan available for the current configuration. Please select a carton or adjust item constraints.
                </p>
              </section>
            )}
          </div>
        )}
      </main>
    </div>
  );
};

export default App;
