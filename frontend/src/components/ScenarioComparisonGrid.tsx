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
        <h3>What-If Packing Scenarios</h3>
        <p className="muted text-xs">
          Click any card to switch the 3D packing preview instantly.
        </p>
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
                <span className={`sc-status-pill is-${status.toLowerCase()}`}>
                  {status === "GREEN" && "🟢 Perfect Fit"}
                  {status === "YELLOW" && `🟡 Elastic Bulge (+${sc.overflow_height_mm}mm)`}
                  {status === "RED" && "🔴 Eject Item"}
                  {status === "BEST_FIT" && "⭐ Best-Fit Optimal"}
                </span>

                {isSelected && <span className="sc-active-indicator">✓ Active 3D</span>}
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
                    <div className="sc-metric">
                      <span className="sc-metric-label">Volume:</span>
                      <strong>{metrics.volume_utilization_pct.toFixed(0)}%</strong>
                    </div>
                    <div className="sc-metric">
                      <span className="sc-metric-label">Items:</span>
                      <strong>
                        {metrics.total_items_packed}
                        {sc.ejected_item_ids && sc.ejected_item_ids.length > 0 && (
                          <span className="ejected-count">
                            {" "}
                            (-{sc.ejected_item_ids.length})
                          </span>
                        )}
                      </strong>
                    </div>
                    <div className="sc-metric">
                      <span className="sc-metric-label">Cost:</span>
                      <strong className="sc-cost">
                        ${metrics.total_estimated_cost_usd.toFixed(2)}
                      </strong>
                    </div>
                  </div>
                )}

                {/* AI Copilot Advice Note */}
                {sc.ai_advisor_note && (
                  <div className="sc-ai-note">
                    <span className="ai-icon">💡</span>
                    <p className="ai-note-text text-xs">{sc.ai_advisor_note}</p>
                  </div>
                )}

                {/* Bulge or Ejection Notice */}
                {status === "YELLOW" && (sc.overflow_height_mm ?? 0) > 0 && (
                  <div className="sc-bulge-notice">
                    <span>⚠️ Lid bulges by ~{sc.overflow_height_mm}mm. Safe to press with H-pattern tape.</span>
                  </div>
                )}
                {status === "RED" && sc.ejected_item_ids && sc.ejected_item_ids.length > 0 && (
                  <div className="sc-eject-notice">
                    <span>📦 Exclude: <strong>{sc.top_item_name || sc.ejected_item_ids.join(", ")}</strong> for separate wrap.</span>
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
                  {isSelected ? "Selected in 3D" : "Inspect in 3D →"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
