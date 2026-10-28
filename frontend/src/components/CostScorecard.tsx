import React from "react";
import { PackingMetrics, ValidationReport } from "../types/contract";

interface CostScorecardProps {
  metrics: PackingMetrics;
  validation: ValidationReport;
}

export const CostScorecard: React.FC<CostScorecardProps> = ({
  metrics,
  validation,
}) => {
  return (
    <div className="card scorecard-card">
      <div className="card-header">
        <h2>Packing & Cost Scorecard</h2>
        <span
          className={`badge ${
            validation.is_valid ? "badge-success" : "badge-danger"
          }`}
        >
          {validation.is_valid ? "Valid Geometry" : "Violations Detected"}
        </span>
      </div>

      <div className="metrics-grid">
        <div className="metric-box highlight">
          <div className="metric-label">Total Estimated Cost</div>
          <div className="metric-value">${metrics.total_estimated_cost_usd.toFixed(2)}</div>
          <div className="metric-sub">Box + Shipping + Void</div>
        </div>

        <div className="metric-box">
          <div className="metric-label">Volume Utilization</div>
          <div className="metric-value">{metrics.volume_utilization_pct.toFixed(1)}%</div>
          <div className="metric-sub">{metrics.total_items_packed} Items Packed</div>
        </div>

        <div className="metric-box">
          <div className="metric-label">Billable Weight</div>
          <div className="metric-value">{metrics.billable_weight_kg.toFixed(2)} kg</div>
          <div className="metric-sub">
            Act: {metrics.actual_gross_weight_kg.toFixed(2)}kg | DIM: {metrics.dim_weight_kg.toFixed(2)}kg
          </div>
        </div>

        <div className="metric-box">
          <div className="metric-label">Shipping Rate</div>
          <div className="metric-value">${metrics.shipping_cost_usd.toFixed(2)}</div>
          <div className="metric-sub">Box: ${metrics.box_cost_usd.toFixed(2)} | Void: ${metrics.void_fill_cost_usd.toFixed(2)}</div>
        </div>
      </div>

      <div className="validation-checks">
        <h3>Deterministic Verification</h3>
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
