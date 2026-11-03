import React, { useState } from "react";
import {
  DetectedItemMeasurement,
  Dimensions3D,
  OrderAnalysisResponse,
  PackingPlan,
  PackingRequest,
  PackingSolutionResponse,
} from "./types/contract";
import { UploadPanel } from "./components/UploadPanel";
import { ExtendedPackableItem, ManifestTable } from "./components/ManifestTable";
import { PackingViewer3D } from "./components/PackingViewer3D";
import { CostScorecard } from "./components/CostScorecard";
import { CartonControlBar } from "./components/CartonControlBar";
import { OptiPackClient } from "./api/optipackClient";
import packingSolutionSample from "./mocks/packingSolutionSample.json";

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
    uncertainty_info: {
      height_sigma_mm: item.uncertainty_mm.height_sigma_mm,
      requires_user_review: item.measurement_provenance.requires_user_review,
    },
  };
};

export const App: React.FC = () => {
  // Clean initial state: Starts empty until user opens camera, uploads photos, or clicks a preset
  const [analysis, setAnalysis] = useState<OrderAnalysisResponse | null>(null);
  const [packableItems, setPackableItems] = useState<ExtendedPackableItem[]>([]);
  const [solution, setSolution] = useState<PackingSolutionResponse | null>(null);
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

  const executePacking = async (
    itemsToPack: ExtendedPackableItem[],
    analysisId: string,
    margin: boolean = applyUncertaintyMargin,
    overrideConfig?: Partial<PackingRequest["solver_config"]>
  ) => {
    if (itemsToPack.length === 0) return;
    setPackingLoading(true);
    const req: PackingRequest = {
      contract_version: "1.0.0",
      analysis_id: analysisId,
      solver_config: {
        mode: "cpsat_with_heuristic_fallback",
        time_limit_ms: 3000,
        apply_uncertainty_margin: margin,
        min_support_ratio: 0.6,
        allow_multi_carton_split: cartonMode === "auto",
        ...(cartonMode === "preset" ? { target_carton_id: selectedCartonSku } : {}),
        ...(cartonMode === "custom" ? { custom_carton_dimensions: customCartonDims } : {}),
        ...overrideConfig,
      },
      items: itemsToPack,
    };

    try {
      const data = await OptiPackClient.packOrder(req);
      setSolution(data);
      setActivePlanIndex(1);
    } catch (err) {
      console.error("[App] Packing optimization failed:", err);
      setSolution(packingSolutionSample as unknown as PackingSolutionResponse);
    } finally {
      setPackingLoading(false);
    }
  };

  const handleAnalysisLoaded = (
    data: OrderAnalysisResponse,
    precomputedSolution?: PackingSolutionResponse
  ) => {
    setAnalysis(data);
    const convertedItems: ExtendedPackableItem[] = data.items.map(convertItem);
    setPackableItems(convertedItems);
    setActivePlanIndex(1);

    if (precomputedSolution) {
      setSolution(precomputedSolution);
    } else if (convertedItems.length > 0) {
      executePacking(convertedItems, data.analysis_id);
    } else {
      setSolution(null);
      const allWarnings = [
        ...(data.global_warnings || []),
        ...(data.calibration?.warnings || []),
      ];
      if (allWarnings.length > 0) {
        console.warn("Analysis Notice:", allWarnings);
      }
    }
  };

  const handleUpdateItem = (index: number, updated: ExtendedPackableItem) => {
    setPackableItems((prev) => {
      const copy = [...prev];
      copy[index] = updated;
      return copy;
    });
  };

  const handleAddItem = () => {
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
      uncertainty_info: {
        height_sigma_mm: 2.0,
        requires_user_review: false,
      },
    };

    setPackableItems((prev) => [...prev, newItem]);
  };

  const handleDeleteItem = (index: number) => {
    setPackableItems((prev) => prev.filter((_, i) => i !== index));
  };

  const handlePackOrder = (overrideConfig?: Partial<PackingRequest["solver_config"]>) => {
    if (!analysis || packableItems.length === 0) return;
    executePacking(packableItems, analysis.analysis_id, applyUncertaintyMargin, overrideConfig);
  };

  const handleReset = () => {
    setAnalysis(null);
    setPackableItems([]);
    setSolution(null);
    setActivePlanIndex(1);
  };

  // Determine active carton plan
  let activePlan: PackingPlan | null = null;
  if (solution?.primary_plan) {
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

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-group">
          <h1>OptiPack</h1>
          <span className="muted">3D Metrology & Volume-First Cartonization</span>
        </div>
      </header>

      <main className="layout">
        <div className="col">
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
            <ManifestTable
              items={packableItems}
              onUpdateItem={handleUpdateItem}
              onAddItem={handleAddItem}
              onDeleteItem={handleDeleteItem}
              onPackOrder={() => handlePackOrder()}
              packingLoading={packingLoading}
              applyUncertaintyMargin={applyUncertaintyMargin}
              setApplyUncertaintyMargin={setApplyUncertaintyMargin}
            />
          )}
        </div>

        <div className="col">
          {packableItems.length > 0 && (
            <CartonControlBar
              cartonMode={cartonMode}
              setCartonMode={(mode) => {
                setCartonMode(mode);
                if (mode === "auto") {
                  handlePackOrder({
                    target_carton_id: undefined,
                    custom_carton_dimensions: undefined,
                  });
                } else if (mode === "preset") {
                  handlePackOrder({
                    target_carton_id: selectedCartonSku,
                    custom_carton_dimensions: undefined,
                  });
                } else if (mode === "custom") {
                  handlePackOrder({
                    target_carton_id: undefined,
                    custom_carton_dimensions: customCartonDims,
                  });
                }
              }}
              selectedCartonSku={selectedCartonSku}
              setSelectedCartonSku={setSelectedCartonSku}
              customCartonDims={customCartonDims}
              setCustomCartonDims={setCustomCartonDims}
              onApply={() => handlePackOrder()}
              loading={packingLoading}
              currentCartonSku={activePlan?.carton.carton_id}
              currentCartonDims={activePlan?.carton.internal_dimensions_mm}
            />
          )}

          {activePlan ? (
            <>
              <CostScorecard
                metrics={activePlan.metrics}
                validation={activePlan.validation}
                carton={activePlan.carton}
                candidateComparison={solution?.candidate_carton_comparison}
                overflowPlans={solution?.overflow_plans}
                unpackedItemIds={solution?.unpacked_item_ids}
                activePlanIndex={activePlanIndex}
                onSelectPlan={setActivePlanIndex}
              />
              <PackingViewer3D plan={activePlan} />
            </>
          ) : solution?.status === "INFEASIBLE" ? (
            <section className="panel" style={{ borderLeft: "4px solid var(--warn, #c93400)" }}>
              <div style={{ padding: "20px 24px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                  <span style={{ fontSize: 20 }}>⚠️</span>
                  <h3 style={{ fontSize: 16, fontWeight: 600 }}>Carton Capacity Exceeded</h3>
                </div>
                <p className="muted text-sm" style={{ marginBottom: 16, lineHeight: 1.5 }}>
                  {String(solution.infeasibility_diagnostics?.reason || "The items do not fit into the selected carton. The item dimensions exceed the internal carton boundaries.")}
                </p>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={() => {
                    setCartonMode("auto");
                    handlePackOrder({
                      target_carton_id: undefined,
                      custom_carton_dimensions: undefined,
                    });
                  }}
                >
                  Switch to Auto-Optimal Carton
                </button>
              </div>
            </section>
          ) : (
            <section className="panel empty">
              <span className="empty-sub-icon">📦</span>
              <p className="muted">
                Capture or upload photos on the left to calculate optimal carton and 3D packing sequence.
              </p>
            </section>
          )}
        </div>
      </main>
    </div>
  );
};

export default App;
