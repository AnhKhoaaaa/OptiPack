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

const usd = (v: number) => `$${v.toFixed(2)}`;

export const CostScorecard: React.FC<CostScorecardProps> = ({
  metrics,
  validation,
  carton,
  candidateComparison = [],
  overflowPlans = [],
  unpackedItemIds = [],
  activePlanIndex = 1,
  onSelectPlan,
}) => {
  const [showDetails, setShowDetails] = useState<boolean>(false);

  const hasMultiple = overflowPlans.length > 0;
  const totalCost =
    metrics.total_estimated_cost_usd +
    overflowPlans.reduce((sum, p) => sum + p.metrics.total_estimated_cost_usd, 0);

  // Savings vs the most expensive feasible candidate in the catalog
  const feasibleCosts = candidateComparison
    .filter((c) => c.feasible && c.total_estimated_cost_usd != null)
    .map((c) => c.total_estimated_cost_usd as number);
  const baseline = feasibleCosts.length > 1 ? Math.max(...feasibleCosts) : null;
  const saved = baseline != null ? Math.max(0, baseline - metrics.total_estimated_cost_usd) : null;

  const checks: [string, boolean][] = [
    ["Inside carton", validation.boundary_check_passed],
    ["No overlap", validation.overlap_check_passed],
    ["Support ≥ 60%", validation.support_check_passed],
    ["Allowed rotations", validation.rotation_check_passed],
    ["Fragility", validation.fragility_check_passed],
    ["Payload limit", validation.weight_check_passed],
  ];
  const passedCount = checks.filter(([, ok]) => ok).length;

  return (
    <section className="panel">
      {hasMultiple && (
        <div className="segmented segmented-block">
          <button
            type="button"
            className={activePlanIndex === 1 ? "is-active" : ""}
            onClick={() => onSelectPlan?.(1)}
          >
            Box 1
          </button>
          {overflowPlans.map((op, idx) => (
            <button
              key={`${op.carton.carton_id}-${idx}`}
              type="button"
              className={activePlanIndex === idx + 2 ? "is-active" : ""}
              onClick={() => onSelectPlan?.(idx + 2)}
            >
              Box {idx + 2}
            </button>
          ))}
        </div>
      )}

      <div className="stats">
        <div className="stat">
          <span className="stat-label">Box</span>
          <span className="stat-value">{carton?.carton_id ?? "—"}</span>
          {carton && (
            <span className="stat-sub">
              {carton.internal_dimensions_mm.length_mm}×{carton.internal_dimensions_mm.width_mm}×
              {carton.internal_dimensions_mm.height_mm} mm
            </span>
          )}
        </div>
        <div className="stat">
          <span className="stat-label">{hasMultiple ? "Total cost" : "Cost"}</span>
          <span className="stat-value">{usd(hasMultiple ? totalCost : metrics.total_estimated_cost_usd)}</span>
          {saved != null && saved > 0 ? (
            <span className="stat-sub positive">Saves {usd(saved)}</span>
          ) : (
            <span className="stat-sub">Lowest cost option</span>
          )}
        </div>
        <div className="stat">
          <span className="stat-label">Space used</span>
          <span className="stat-value">{metrics.volume_utilization_pct.toFixed(0)}%</span>
          <div className="meter">
            <div style={{ width: `${Math.min(100, metrics.volume_utilization_pct)}%` }} />
          </div>
        </div>
      </div>

      {(unpackedItemIds.length > 0 || !validation.is_valid) && (
        <p className="notice">
          {unpackedItemIds.length > 0
            ? `${unpackedItemIds.length} item(s) don't fit any carton.`
            : `${6 - passedCount} geometry check(s) failed.`}
        </p>
      )}

      <button
        type="button"
        className="disclosure"
        onClick={() => setShowDetails((v) => !v)}
        aria-expanded={showDetails}
      >
        <span className={`chevron ${showDetails ? "open" : ""}`}>›</span>
        Details
        <span className="muted">{passedCount}/6 checks passed</span>
      </button>

      {showDetails && (
        <div className="details">
          <dl className="kv">
            <dt>Box</dt>
            <dd>{usd(metrics.box_cost_usd)}</dd>
            <dt>Void fill</dt>
            <dd>{usd(metrics.void_fill_cost_usd)}</dd>
            <dt>Shipping</dt>
            <dd>{usd(metrics.shipping_cost_usd)}</dd>
            <dt>Billable weight</dt>
            <dd>
              {metrics.billable_weight_kg.toFixed(2)} kg
              <span className="muted">
                {" "}
                (actual {metrics.actual_gross_weight_kg.toFixed(2)}, DIM {metrics.dim_weight_kg.toFixed(2)})
              </span>
            </dd>
          </dl>

          {candidateComparison.length > 0 && (
            <table className="compare">
              <thead>
                <tr>
                  <th>Carton</th>
                  <th className="right">Cost</th>
                  <th className="right">Used</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {candidateComparison.map((c) => (
                  <tr key={c.carton_id} className={c.selected ? "is-selected" : !c.feasible ? "is-dim" : ""}>
                    <td>{c.carton_id}</td>
                    <td className="right">
                      {c.total_estimated_cost_usd != null ? usd(c.total_estimated_cost_usd) : "—"}
                    </td>
                    <td className="right">
                      {c.volume_utilization_pct != null ? `${c.volume_utilization_pct.toFixed(0)}%` : "—"}
                    </td>
                    <td className="muted truncate">
                      {c.selected ? "Selected" : c.rejection_reason || (c.feasible ? "Higher cost" : "Doesn't fit")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <ul className="checks">
            {checks.map(([label, ok]) => (
              <li key={label} className={ok ? "ok" : "fail"}>
                {ok ? "✓" : "✕"} {label}
              </li>
            ))}
          </ul>

          {validation.violations.length > 0 && (
            <ul className="violations">
              {validation.violations.map((v, i) => (
                <li key={i}>{v}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
};
