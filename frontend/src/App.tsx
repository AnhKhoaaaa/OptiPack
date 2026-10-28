import React, { useState } from "react";
import {
  OrderAnalysisResponse,
  PackableItem,
  PackingPlan,
  PackingRequest,
  PackingSolutionResponse,
} from "./types/contract";
import { UploadPanel } from "./components/UploadPanel";
import { ManifestTable } from "./components/ManifestTable";
import { PackingViewer3D } from "./components/PackingViewer3D";
import { CostScorecard } from "./components/CostScorecard";
import packingSolutionSample from "./mocks/packingSolutionSample.json";

export const App: React.FC = () => {
  const [analysis, setAnalysis] = useState<OrderAnalysisResponse | null>(null);
  const [packableItems, setPackableItems] = useState<PackableItem[]>([]);
  const [packingPlan, setPackingPlan] = useState<PackingPlan | null>(
    (packingSolutionSample as unknown as PackingSolutionResponse).primary_plan
  );
  const [loading, setLoading] = useState<boolean>(false);
  const [packingLoading, setPackingLoading] = useState<boolean>(false);

  const handleAnalysisLoaded = (data: OrderAnalysisResponse) => {
    setAnalysis(data);
    const convertedItems: PackableItem[] = data.items.map((item) => ({
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
    }));
    setPackableItems(convertedItems);
  };

  const handleUpdateItem = (index: number, updated: PackableItem) => {
    setPackableItems((prev) => {
      const copy = [...prev];
      copy[index] = updated;
      return copy;
    });
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
        apply_uncertainty_margin: true,
        min_support_ratio: 0.6,
        allow_multi_carton_split: true,
      },
      items: packableItems,
    };

    try {
      const res = await fetch("http://localhost:8000/api/v1/orders/pack", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data: PackingSolutionResponse = await res.json();
      if (data.primary_plan) {
        setPackingPlan(data.primary_plan);
      } else {
        alert("Order items cannot fit into a single carton. Split carton required.");
      }
    } catch (err) {
      console.warn("Backend not reached, falling back to mock solution.", err);
      setPackingPlan(
        (packingSolutionSample as unknown as PackingSolutionResponse).primary_plan
      );
    } finally {
      setPackingLoading(false);
    }
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-brand">
          <div className="logo-icon">📦</div>
          <div>
            <h1>OptiPack</h1>
            <p className="subtitle">AI & 3D Cartonization Assistant (Contract v1.0.0)</p>
          </div>
        </div>
        <div className="header-meta">
          <span className="badge badge-outline">Meta Model API</span>
          <span className="badge badge-outline">OR-Tools CP-SAT</span>
          <span className="badge badge-outline">Three.js</span>
        </div>
      </header>

      <main className="app-main">
        <div className="grid-layout">
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
                onPackOrder={handlePackOrder}
                packingLoading={packingLoading}
              />
            )}
          </div>

          <div className="grid-column-right">
            {packingPlan ? (
              <>
                <PackingViewer3D plan={packingPlan} />
                <CostScorecard
                  metrics={packingPlan.metrics}
                  validation={packingPlan.validation}
                />
              </>
            ) : (
              <div className="card placeholder-card">
                <h3>Packing Viewer Ready</h3>
                <p>Analyze an order or load the demo preset to preview optimal cartonization and 3D steps.</p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default App;
