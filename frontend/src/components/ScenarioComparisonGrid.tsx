import React from "react";
import { PackingScenarioCard } from "../types/contract";

interface ScenarioComparisonGridProps {
  scenarios: PackingScenarioCard[];
  selectedScenarioId: string | null;
  onSelectScenario: (scenario: PackingScenarioCard) => void;
}

export const ScenarioComparisonGrid: React.FC<ScenarioComparisonGridProps> = ({
  scenarios,
  selectedScenarioId,
  onSelectScenario,
}) => {
  if (!scenarios || scenarios.length === 0) return null;

  return (
    <div className="scenarios-container">
      <div className="scenarios-header">
        <h3>Packing Options</h3>
      </div>

      <div className="scenarios-grid">
        {scenarios.map((sc) => {
          const isSelected = selectedScenarioId === sc.scenario_id;
          const status = sc.badge_status;
          const plan = sc.plan;
          const metrics = plan?.metrics;
          const carton = plan?.carton;

          const cardClass = `scenario-card is-${status.toLowerCase()} ${
            isSelected ? "is-active" : ""
          }`;

          return (
            <div
              key={sc.scenario_id}
              className={cardClass}
              onClick={() => onSelectScenario(sc)}
              role="button"
              tabIndex={0}
            >
              {/* Card Header & Badge */}
              <div className="sc-card-head">
                <div className={`sc-status-pill is-${status.toLowerCase()}`}>
                  <span className={`sc-status-dot is-${status.toLowerCase()}`} />
                  <span className="sc-status-text">
                    {status === "GREEN" && "Snug Fit"}
                    {status === "YELLOW" && `Lid Flex (+${sc.overflow_height_mm}mm)`}
                    {status === "RED" && "2-Box Split"}
                    {status === "BEST_FIT" && "Optimal Catalog"}
                  </span>
                </div>

                {isSelected && (
                  <span className="sc-active-indicator">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                    <span>Active</span>
                  </span>
                )}
              </div>

              {/* Title & Carton Dimensions */}
              <div className="sc-card-body">
                <h4 className="sc-title">{sc.title}</h4>
                {carton && (
                  <span className="sc-dims text-xs muted">
                    {carton.carton_id} · {carton.internal_dimensions_mm.length_mm} ×{" "}
                    {carton.internal_dimensions_mm.width_mm} ×{" "}
                    {carton.internal_dimensions_mm.height_mm} mm
                  </span>
                )}

                {/* Key Metrics row */}
                {metrics && (
                  <div className="sc-metrics-row">
                    <span className="sc-metric-inline text-xs">
                      <strong>{metrics.volume_utilization_pct.toFixed(0)}%</strong> vol ·{" "}
                      <strong>{metrics.total_items_packed}</strong> items ·{" "}
                      <strong className="sc-cost">
                        ${metrics.total_estimated_cost_usd.toFixed(2)}
                      </strong>
                    </span>
                  </div>
                )}

                {/* AI Copilot Advice Note */}
                {sc.ai_advisor_note && (
                  <div className="sc-ai-note">
                    <p className="ai-note-text text-xs">{sc.ai_advisor_note}</p>
                  </div>
                )}

                {/* Bulge or Ejection Notice */}
                {status === "YELLOW" && (sc.overflow_height_mm ?? 0) > 0 && (
                  <div className="sc-bulge-notice">
                    <span>Lid flexes +{sc.overflow_height_mm}mm. Safe to seal with H-tape.</span>
                  </div>
                )}
                {status === "RED" && sc.ejected_item_ids && sc.ejected_item_ids.length > 0 && (
                  <div className="sc-eject-notice">
                    <span>Ship <strong>{sc.top_item_name || "item"}</strong> in separate mailer.</span>
                  </div>
                )}
              </div>

              <div className="sc-card-foot">
                <button
                  type="button"
                  className={`btn btn-sm ${isSelected ? "btn-primary" : "btn-secondary"}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectScenario(sc);
                  }}
                >
                  {isSelected ? "Active" : "View 3D"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
