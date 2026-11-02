import React, { useState } from "react";
import {
  CandidateCartonEvaluation,
  CartonSpec,
  PackingMetrics,
  PackingPlan,
  ValidationReport,
} from "../types/contract";

interface CostScorecardProps {
  metrics: PackingMetrics;
  validation: ValidationReport;
  carton?: CartonSpec;
  candidateComparison?: CandidateCartonEvaluation[];
  overflowPlans?: PackingPlan[];
  unpackedItemIds?: string[];
  activePlanIndex?: number;
  onSelectPlan?: (index: number) => void;
}

interface CartonMeta {
  dimensions: string;
  volumeL: number;
  maxPayloadKg: number;
  name: string;
}

export const STANDARD_CARTON_SPECS: Record<string, CartonMeta> = {
  "BOX-S": { dimensions: "200 × 150 × 100 mm", volumeL: 3.0, maxPayloadKg: 3.0, name: "Small Mailer Box" },
  "BOX-M": { dimensions: "300 × 220 × 150 mm", volumeL: 9.9, maxPayloadKg: 8.0, name: "Medium Standard Carton" },
  "BOX-L": { dimensions: "400 × 300 × 200 mm", volumeL: 24.0, maxPayloadKg: 15.0, name: "Large E-Commerce Carton" },
  "BOX-XL": { dimensions: "500 × 350 × 250 mm", volumeL: 43.8, maxPayloadKg: 20.0, name: "Extra-Large Fulfillment Box" },
  "BOX-XXL": { dimensions: "600 × 400 × 350 mm", volumeL: 84.0, maxPayloadKg: 25.0, name: "Heavy Bulk Master Carton" },
};

export const CostScorecard: React.FC<CostScorecardProps> = ({
  metrics,
  validation,
  carton,
  candidateComparison,
  overflowPlans = [],
  unpackedItemIds = [],
  activePlanIndex = 1,
  onSelectPlan,
}) => {
  const [showComparison, setShowComparison] = useState<boolean>(true);
  const [showCostReference, setShowCostReference] = useState<boolean>(false);

  const hasMultipleCartons = overflowPlans.length > 0;

  // Derive volume and void slack in Liters
  const cartonDims = carton?.internal_dimensions_mm;
  const cartonVolLiters = cartonDims
    ? ((cartonDims.length_mm * cartonDims.width_mm * cartonDims.height_mm) / 1_000_000).toFixed(1)
    : (STANDARD_CARTON_SPECS[carton?.carton_id || "BOX-M"]?.volumeL.toFixed(1) || "9.9");

  // Void volume in liters calculated from void cost ($0.04/L)
  const voidLiters = (metrics.void_fill_cost_usd / 0.04).toFixed(1);

  // Total volume across all multi-carton split boxes
  const totalCombinedVolumeL = (
    parseFloat(cartonVolLiters) +
    overflowPlans.reduce((sum, p) => {
      const d = p.carton.internal_dimensions_mm;
      return sum + (d.length_mm * d.width_mm * d.height_mm) / 1_000_000;
    }, 0)
  ).toFixed(1);

  return (
    <div className="card scorecard-card">
      <div className="card-header">
        <div className="scorecard-title-group">
          <h2>4. Packing & Space Efficiency Scorecard</h2>
          <span
            className={`badge ${
              validation.is_valid ? "badge-success" : "badge-danger"
            }`}
          >
            {validation.is_valid ? "✓ Valid Geometry" : "✗ Violations Detected"}
          </span>
        </div>

        {hasMultipleCartons && (
          <span className="badge badge-warning">
            Multi-Carton Split Required ({overflowPlans.length + 1} Boxes)
          </span>
        )}
      </div>

      {/* Multi-Carton Tab Switcher (if order split into Box 1, Box 2) */}
      {hasMultipleCartons && (
        <div className="multi-carton-banner">
          <div className="multi-carton-tabs">
            <button
              className={`carton-tab ${activePlanIndex === 1 ? "active" : ""}`}
              onClick={() => onSelectPlan && onSelectPlan(1)}
            >
              <strong>Carton 1 (Primary: {carton?.carton_id || "BOX-M"})</strong>
              <span>{cartonDims ? `${cartonDims.length_mm}×${cartonDims.width_mm}×${cartonDims.height_mm} mm` : "Standard"} ({cartonVolLiters}L)</span>
            </button>

            {overflowPlans.map((op, idx) => {
              const opDims = op.carton.internal_dimensions_mm;
              const opVolL = ((opDims.length_mm * opDims.width_mm * opDims.height_mm) / 1_000_000).toFixed(1);
              return (
                <button
                  key={op.carton.carton_id}
                  className={`carton-tab ${activePlanIndex === idx + 2 ? "active" : ""}`}
                  onClick={() => onSelectPlan && onSelectPlan(idx + 2)}
                >
                  <strong>Carton {idx + 2} ({op.carton.carton_id})</strong>
                  <span>{opDims.length_mm}×{opDims.width_mm}×{opDims.height_mm} mm ({opVolL}L)</span>
                </button>
              );
            })}
          </div>

          <div className="multi-carton-total">
            Total Containers: <strong>{overflowPlans.length + 1} Boxes</strong> • Combined Volume: <strong>{totalCombinedVolumeL} Liters</strong>
          </div>
        </div>
      )}

      {/* Unpacked items warning */}
      {unpackedItemIds.length > 0 && (
        <div className="violations-box">
          <strong>⚠️ Infeasibility Alert:</strong> {unpackedItemIds.length} items could not fit into any carton in the catalog:
          <span style={{ marginLeft: 6, fontFamily: "var(--font-mono)" }}>
            [{unpackedItemIds.join(", ")}]
          </span>
        </div>
      )}

      {/* 4 Physical & Operational KPIs */}
      <div className="metrics-grid">
        <div className="metric-box highlight">
          <div className="metric-label">Recommended Box Size</div>
          <div className="metric-value">{carton?.carton_id || "BOX-M"}</div>
          <div className="metric-sub">
            {cartonDims
              ? `${cartonDims.length_mm} × ${cartonDims.width_mm} × ${cartonDims.height_mm} mm (${cartonVolLiters}L)`
              : "Standard Die-Cut Carton"}
          </div>
        </div>

        <div className="metric-box">
          <div className="metric-label">Space Utilization</div>
          <div className="metric-value">{metrics.volume_utilization_pct.toFixed(1)}%</div>
          <div className="metric-sub">
            {metrics.total_items_packed} Items Packed • {voidLiters}L Void Slack
          </div>
        </div>

        <div className="metric-box">
          <div className="metric-label">Billable Weight Tier</div>
          <div className="metric-value">{metrics.billable_weight_kg.toFixed(2)} kg</div>
          <div className="metric-sub">
            Actual: {metrics.actual_gross_weight_kg.toFixed(2)}kg • DIM: {metrics.dim_weight_kg.toFixed(2)}kg
          </div>
        </div>

        <div className="metric-box">
          <div className="metric-label">Load Physics & Stability</div>
          <div className="metric-value">{validation.is_valid ? "6/6 Passed" : "Review"}</div>
          <div className="metric-sub">
            Tare: {carton ? carton.tare_weight_g : 160}g • Max: {carton ? (carton.max_payload_g / 1000).toFixed(1) : "8.0"}kg
          </div>
        </div>
      </div>

      {/* Optional Financial Cost Reference Accordion */}
      <div className="financial-reference-card">
        <div
          className="financial-reference-header"
          onClick={() => setShowCostReference((prev) => !prev)}
        >
          <span>
            {showCostReference ? "▼" : "▶"} Carrier Freight & Material Cost Reference (USD Indicator)
          </span>
          <span className="comparison-toggle-text">
            {showCostReference ? "Hide" : "Show Estimation"}
          </span>
        </div>

        {showCostReference && (
          <div className="financial-reference-content">
            <div className="cost-breakdown-row">
              <span className="cost-item">
                📦 Box Material: <strong>${metrics.box_cost_usd.toFixed(2)} USD</strong>
              </span>
              <span className="cost-divider">•</span>
              <span className="cost-item">
                🚚 Carrier Rate: <strong>${metrics.shipping_cost_usd.toFixed(2)} USD</strong> (DIM Divisor 5000)
              </span>
              <span className="cost-divider">•</span>
              <span className="cost-item">
                🫧 Void Cushion: <strong>${metrics.void_fill_cost_usd.toFixed(2)} USD</strong>
              </span>
              <span className="cost-divider">•</span>
              <span className="cost-item highlight">
                Total Estimated: <strong>${metrics.total_estimated_cost_usd.toFixed(2)} USD</strong>
              </span>
            </div>
            <p className="cost-disclaimer-note">
              * Note: Financial costs are indicative baseline estimates. Warehouse packing optimization is primarily governed by minimal bounding volume and 3D structural stability.
            </p>
          </div>
        )}
      </div>

      {/* Candidate Carton Evaluation Table */}
      {candidateComparison && candidateComparison.length > 0 && (
        <div className="comparison-section">
          <div className="comparison-header" onClick={() => setShowComparison((prev) => !prev)}>
            <h3>
              {showComparison ? "▼" : "▶"} Candidate Carton Evaluation (Why this carton?)
            </h3>
            <span className="comparison-toggle-text">
              {showComparison ? "Collapse" : "Expand"}
            </span>
          </div>

          {showComparison && (
            <div className="table-responsive">
              <table className="comparison-table">
                <thead>
                  <tr>
                    <th>Carton SKU</th>
                    <th>Usable Dimensions (L × W × H)</th>
                    <th>Usable Vol.</th>
                    <th>Max Payload</th>
                    <th>Feasibility</th>
                    <th>Space Util.</th>
                    <th>Solver Selection Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {candidateComparison.map((cand) => {
                    const meta = STANDARD_CARTON_SPECS[cand.carton_id];
                    return (
                      <tr
                        key={cand.carton_id}
                        className={cand.selected ? "row-selected-carton" : ""}
                      >
                        <td>
                          <strong>{cand.carton_id}</strong>
                          {cand.selected && (
                            <span className="badge badge-success" style={{ marginLeft: 6 }}>
                              SELECTED
                            </span>
                          )}
                        </td>
                        <td className="dimensions-mono">
                          {meta ? meta.dimensions : "Standard"}
                        </td>
                        <td>{meta ? `${meta.volumeL} L` : "—"}</td>
                        <td>{meta ? `${meta.maxPayloadKg} kg` : "—"}</td>
                        <td>
                          <span
                            className={`badge ${
                              cand.feasible ? "badge-success" : "badge-danger"
                            }`}
                          >
                            {cand.feasible ? "Feasible" : "Rejected"}
                          </span>
                        </td>
                        <td>
                          {cand.volume_utilization_pct != null
                            ? `${cand.volume_utilization_pct.toFixed(1)}%`
                            : "—"}
                        </td>
                        <td className="rejection-cell">
                          {cand.selected
                            ? "✓ Optimal: Smallest feasible carton with maximum space utilization."
                            : cand.rejection_reason || "Suboptimal carton volume tier."}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Deterministic Verification Checklist */}
      <div className="validation-checks">
        <h3>Independent Deterministic Geometry Validation (6/6 Checks)</h3>
        <ul className="check-list">
          <li className={validation.boundary_check_passed ? "passed" : "failed"}>
            {validation.boundary_check_passed ? "✓" : "✗"} Boundary Containment (100% inside carton)
          </li>
          <li className={validation.overlap_check_passed ? "passed" : "failed"}>
            {validation.overlap_check_passed ? "✓" : "✗"} Zero Pairwise 3D Collision / Overlap
          </li>
          <li className={validation.support_check_passed ? "passed" : "failed"}>
            {validation.support_check_passed ? "✓" : "✗"} Vertical Support Coverage (≥ 60%)
          </li>
          <li className={validation.rotation_check_passed ? "passed" : "failed"}>
            {validation.rotation_check_passed ? "✓" : "✗"} Allowed Rotations & Upright Rule
          </li>
          <li className={validation.fragility_check_passed ? "passed" : "failed"}>
            {validation.fragility_check_passed ? "✓" : "✗"} Fragility & Top-Load Safety
          </li>
          <li className={validation.weight_check_passed ? "passed" : "failed"}>
            {validation.weight_check_passed ? "✓" : "✗"} Maximum Payload Limit
          </li>
        </ul>

        {validation.violations.length > 0 && (
          <div className="violations-box">
            <h4>Violations:</h4>
            <ul>
              {validation.violations.map((v, i) => (
                <li key={i}>{v}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};
