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
  const cartonDims = carton?.internal_dimensions_mm;
  const cartonVolLiters = cartonDims
    ? ((cartonDims.length_mm * cartonDims.width_mm * cartonDims.height_mm) / 1_000_000).toFixed(1)
    : STANDARD_CARTON_SPECS[carton?.carton_id || "BOX-M"]?.volumeL.toFixed(1) || "9.9";

  // Void volume in liters calculated from void cost ($0.04/L)
  const voidLiters = (metrics.void_fill_cost_usd / 0.04).toFixed(1);

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
            Box 1 · {carton?.carton_id || "BOX-M"} ({cartonVolLiters}L)
          </button>
          {overflowPlans.map((op, idx) => {
            const d = op.carton.internal_dimensions_mm;
            const opVolL = ((d.length_mm * d.width_mm * d.height_mm) / 1_000_000).toFixed(1);
            return (
              <button
                key={`${op.carton.carton_id}-${idx}`}
                type="button"
                className={activePlanIndex === idx + 2 ? "is-active" : ""}
                onClick={() => onSelectPlan?.(idx + 2)}
              >
                Box {idx + 2} · {op.carton.carton_id} ({opVolL}L)
              </button>
            );
          })}
        </div>
      )}

      <div className="stats">
        <div className="stat">
          <span className="stat-label">Recommended Box</span>
          <span className="stat-value">{carton?.carton_id ?? "—"}</span>
          {cartonDims && (
            <span className="stat-sub">
              {cartonDims.length_mm}×{cartonDims.width_mm}×{cartonDims.height_mm} mm ({cartonVolLiters} L)
            </span>
          )}
        </div>
        <div className="stat">
          <span className="stat-label">Space Used</span>
          <span className="stat-value">{metrics.volume_utilization_pct.toFixed(1)}%</span>
          <div className="meter">
            <div style={{ width: `${Math.min(100, metrics.volume_utilization_pct)}%` }} />
          </div>
          <span className="stat-sub">{voidLiters} L void slack</span>
        </div>
        <div className="stat">
          <span className="stat-label">Billable Weight</span>
          <span className="stat-value">{metrics.billable_weight_kg.toFixed(2)} kg</span>
          <span className={`stat-sub ${validation.is_valid ? "positive" : ""}`}>
            {passedCount}/6 physics checks · {usd(metrics.total_estimated_cost_usd)} est.
          </span>
        </div>
      </div>

      {(unpackedItemIds.length > 0 || !validation.is_valid) && (
        <p className="notice">
          {unpackedItemIds.length > 0
            ? `${unpackedItemIds.length} item(s) don't fit any carton: ${unpackedItemIds.join(", ")}`
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
        Details & Catalog Comparison
        <span className="muted">
          {metrics.total_items_packed} items packed · {passedCount}/6 checks passed
        </span>
      </button>

      {showDetails && (
        <div className="details">
          <dl className="kv">
            <dt>Gross vs. DIM weight</dt>
            <dd>
              {metrics.actual_gross_weight_kg.toFixed(2)} kg actual / {metrics.dim_weight_kg.toFixed(2)} kg DIM
            </dd>
            <dt>Center of mass (X, Y, Z)</dt>
            <dd>
              ({metrics.center_of_mass_mm.x.toFixed(0)}, {metrics.center_of_mass_mm.y.toFixed(0)},{" "}
              {metrics.center_of_mass_mm.z.toFixed(0)}) mm
            </dd>
            <dt>Reference cost breakdown</dt>
            <dd>
              Box {usd(metrics.box_cost_usd)} · Void fill {usd(metrics.void_fill_cost_usd)} · Shipping{" "}
              {usd(metrics.shipping_cost_usd)}
            </dd>
          </dl>

          {candidateComparison.length > 0 && (
            <table className="compare">
              <thead>
                <tr>
                  <th>Carton</th>
                  <th>Dimensions</th>
                  <th className="right">Used</th>
                  <th>Selection Note</th>
                </tr>
              </thead>
              <tbody>
                {candidateComparison.map((c) => {
                  const meta = STANDARD_CARTON_SPECS[c.carton_id];
                  return (
                    <tr
                      key={c.carton_id}
                      className={c.selected ? "is-selected" : !c.feasible ? "is-dim" : ""}
                    >
                      <td>{c.carton_id}</td>
                      <td className="muted">{meta ? `${meta.dimensions} (${meta.volumeL}L)` : "Custom"}</td>
                      <td className="right">
                        {c.volume_utilization_pct != null ? `${c.volume_utilization_pct.toFixed(1)}%` : "—"}
                      </td>
                      <td className="muted truncate">
                        {c.selected
                          ? "✓ Selected (smallest feasible volume)"
                          : c.rejection_reason || (c.feasible ? "Larger carton volume tier" : "Doesn't fit")}
                      </td>
                    </tr>
                  );
                })}
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
