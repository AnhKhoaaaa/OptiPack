import React, { useState } from "react";
import {
  CandidateCartonEvaluation,
  PackingMetrics,
  PackingPlan,
  ValidationReport,
} from "../types/contract";

interface CostScorecardProps {
  metrics: PackingMetrics;
  validation: ValidationReport;
  candidateComparison?: CandidateCartonEvaluation[];
  overflowPlans?: PackingPlan[];
  unpackedItemIds?: string[];
  activePlanIndex?: number;
  onSelectPlan?: (index: number) => void;
}

export const CostScorecard: React.FC<CostScorecardProps> = ({
  metrics,
  validation,
  candidateComparison,
  overflowPlans = [],
  unpackedItemIds = [],
  activePlanIndex = 1,
  onSelectPlan,
}) => {
  const [showComparison, setShowComparison] = useState<boolean>(true);

  const hasMultipleCartons = overflowPlans.length > 0;
  const totalCombinedCost =
    metrics.total_estimated_cost_usd +
    overflowPlans.reduce((sum, p) => sum + p.metrics.total_estimated_cost_usd, 0);

  return (
    <div className="card scorecard-card">
      <div className="card-header">
        <div className="scorecard-title-group">
          <h2>4. Packing & Cost Optimization Scorecard</h2>
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
              <strong>Carton 1 (Primary)</strong>
              <span>${metrics.total_estimated_cost_usd.toFixed(2)} USD</span>
            </button>

            {overflowPlans.map((op, idx) => (
              <button
                key={op.carton.carton_id}
                className={`carton-tab ${activePlanIndex === idx + 2 ? "active" : ""}`}
                onClick={() => onSelectPlan && onSelectPlan(idx + 2)}
              >
                <strong>Carton {idx + 2} ({op.carton.carton_id})</strong>
                <span>${op.metrics.total_estimated_cost_usd.toFixed(2)} USD</span>
              </button>
            ))}
          </div>

          <div className="multi-carton-total">
            Combined Total Cost: <strong>${totalCombinedCost.toFixed(2)} USD</strong>
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

      {/* 4 Financial & Volumetric KPIs */}
      <div className="metrics-grid">
        <div className="metric-box highlight">
          <div className="metric-label">Total Estimated Cost</div>
          <div className="metric-value">${metrics.total_estimated_cost_usd.toFixed(2)}</div>
          <div className="metric-sub">Box: ${metrics.box_cost_usd.toFixed(2)} | Void: ${metrics.void_fill_cost_usd.toFixed(2)}</div>
        </div>

        <div className="metric-box">
          <div className="metric-label">Volume Utilization</div>
          <div className="metric-value">{metrics.volume_utilization_pct.toFixed(1)}%</div>
          <div className="metric-sub">{metrics.total_items_packed} Items in this box</div>
        </div>

        <div className="metric-box">
          <div className="metric-label">Billable Weight</div>
          <div className="metric-value">{metrics.billable_weight_kg.toFixed(2)} kg</div>
          <div className="metric-sub">
            Act: {metrics.actual_gross_weight_kg.toFixed(2)}kg | DIM: {metrics.dim_weight_kg.toFixed(2)}kg
          </div>
        </div>

        <div className="metric-box">
          <div className="metric-label">Carrier Shipping Rate</div>
          <div className="metric-value">${metrics.shipping_cost_usd.toFixed(2)}</div>
          <div className="metric-sub">Divisor: 5,000 cm³/kg</div>
        </div>
      </div>

      {/* Candidate Carton Comparison Table (Explains why BOX-M was chosen over BOX-S / BOX-L) */}
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
                    <th>Carton Catalog</th>
                    <th>Feasibility</th>
                    <th>Est. Total Cost</th>
                    <th>Volume Util.</th>
                    <th>Solver Selection Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {candidateComparison.map((cand) => (
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
                        {cand.total_estimated_cost_usd != null
                          ? `$${cand.total_estimated_cost_usd.toFixed(2)} USD`
                          : "—"}
                      </td>
                      <td>
                        {cand.volume_utilization_pct != null
                          ? `${cand.volume_utilization_pct.toFixed(1)}%`
                          : "—"}
                      </td>
                      <td className="rejection-cell">
                        {cand.selected
                          ? "✓ Cost-optimal packaging & lowest billable DIM weight tier."
                          : cand.rejection_reason || "Suboptimal cost tier."}
                      </td>
                    </tr>
                  ))}
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
