import React, { useState } from "react";
import {
  OrderAnalysisResponse,
  PackingPlan,
  PackingRequest,
  PackingSolutionResponse,
} from "./types/contract";
import { UploadPanel } from "./components/UploadPanel";
import { ExtendedPackableItem, ManifestTable } from "./components/ManifestTable";
import { PackingViewer3D } from "./components/PackingViewer3D";
import { CostScorecard } from "./components/CostScorecard";
import { OptiPackClient } from "./api/optipackClient";
import orderAnalysisSample from "./mocks/orderAnalysisSample.json";
import packingSolutionSample from "./mocks/packingSolutionSample.json";

export const App: React.FC = () => {
  // Convert initial sample items
  const initialItems: ExtendedPackableItem[] = (
    orderAnalysisSample as unknown as OrderAnalysisResponse
  ).items.map((item) => ({
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
    uncertainty_info: {
      height_sigma_mm: item.uncertainty_mm.height_sigma_mm,
      requires_user_review: item.measurement_provenance.requires_user_review,
    },
  }));

  const [analysis, setAnalysis] = useState<OrderAnalysisResponse | null>(
    orderAnalysisSample as unknown as OrderAnalysisResponse
  );
  const [packableItems, setPackableItems] = useState<ExtendedPackableItem[]>(initialItems);
  const [solution, setSolution] = useState<PackingSolutionResponse | null>(
    packingSolutionSample as unknown as PackingSolutionResponse
  );
  const [activePlanIndex, setActivePlanIndex] = useState<number>(1);
  const [applyUncertaintyMargin, setApplyUncertaintyMargin] = useState<boolean>(true);

  const [loading, setLoading] = useState<boolean>(false);
  const [packingLoading, setPackingLoading] = useState<boolean>(false);

  const handleAnalysisLoaded = (
    data: OrderAnalysisResponse,
    precomputedSolution?: PackingSolutionResponse
  ) => {
    setAnalysis(data);
    const convertedItems: ExtendedPackableItem[] = data.items.map((item) => ({
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
      uncertainty_info: {
        height_sigma_mm: item.uncertainty_mm.height_sigma_mm,
        requires_user_review: item.measurement_provenance.requires_user_review,
      },
    }));
    setPackableItems(convertedItems);
    setActivePlanIndex(1);

    if (precomputedSolution) {
      setSolution(precomputedSolution);
    } else {
      setSolution(packingSolutionSample as unknown as PackingSolutionResponse);
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
    const newItemId = `item_custom_${packableItems.length + 1}`;
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

  const handlePackOrder = async () => {
    if (!analysis || packableItems.length === 0) return;

    setPackingLoading(true);
    const req: PackingRequest = {
      contract_version: "1.0.0",
      analysis_id: analysis.analysis_id,
      solver_config: {
        mode: "cpsat_with_heuristic_fallback",
        time_limit_ms: 3000,
        apply_uncertainty_margin: applyUncertaintyMargin,
        min_support_ratio: 0.6,
        allow_multi_carton_split: true,
      },
      items: packableItems,
    };

    try {
      const data = await OptiPackClient.packOrder(req);
      setSolution(data);
      setActivePlanIndex(1);
    } catch (err) {
      console.error("[App] Packing optimization failed:", err);
      alert(`Tối ưu hóa đóng gói thất bại: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setPackingLoading(false);
    }
  };

  // Determine which plan is displayed in the 3D viewer (Carton 1 vs Carton 2...)
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
    <div className="app-container">
      {/* Top Header */}
      <header className="app-header">
        <div className="header-brand">
          <div className="logo-icon">📦</div>
          <div>
            <h1>OptiPack</h1>
            <p className="subtitle">AI & 3D Multi-Item Cartonization MVP (Contract v1.0.0)</p>
          </div>
        </div>
        <div className="header-meta">
          <span className="badge badge-meta">Meta Model API (muse-spark-1.3)</span>
          <span className="badge badge-solver">OR-Tools CP-SAT</span>
          <span className="badge badge-three">Three.js Y-Up</span>
          <span className="badge badge-outline">Member 4 UI</span>
        </div>
      </header>

      {/* Main Split Grid */}
      <main className="app-main">
        <div className="grid-layout">
          {/* Left Column: Input, Metrology & Manifest */}
          <div className="grid-column-left">
            <UploadPanel
              onAnalysisLoaded={handleAnalysisLoaded}
              loading={loading}
              setLoading={setLoading}
            />

            {packableItems.length > 0 && (
              <ManifestTable
                items={packableItems}
                onUpdateItem={handleUpdateItem}
                onAddItem={handleAddItem}
                onDeleteItem={handleDeleteItem}
                onPackOrder={handlePackOrder}
                packingLoading={packingLoading}
                applyUncertaintyMargin={applyUncertaintyMargin}
                setApplyUncertaintyMargin={setApplyUncertaintyMargin}
              />
            )}
          </div>

          {/* Right Column: 3D Visualization & Cost Scorecard */}
          <div className="grid-column-right">
            {activePlan ? (
              <>
                <PackingViewer3D plan={activePlan} />
                <CostScorecard
                  metrics={activePlan.metrics}
                  validation={activePlan.validation}
                  candidateComparison={solution?.candidate_carton_comparison}
                  overflowPlans={solution?.overflow_plans}
                  unpackedItemIds={solution?.unpacked_item_ids}
                  activePlanIndex={activePlanIndex}
                  onSelectPlan={setActivePlanIndex}
                />
              </>
            ) : (
              <div className="card placeholder-card">
                <h3>Packing Viewer Ready</h3>
                <p>
                  Upload packing images or load one of the 3 Demo Presets on the left to inspect 3D packing sequence.
                </p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default App;
