import React from "react";
import { PackableItem, RotationCode } from "../types/contract";

export interface ExtendedPackableItem extends PackableItem {
  uncertainty_info?: {
    height_sigma_mm: number;
    requires_user_review: boolean;
  };
}

interface ManifestTableProps {
  items: ExtendedPackableItem[];
  onUpdateItem: (index: number, updated: ExtendedPackableItem) => void;
  onAddItem: () => void;
  onDeleteItem: (index: number) => void;
  onPackOrder: () => void;
  packingLoading: boolean;
  applyUncertaintyMargin: boolean;
  setApplyUncertaintyMargin: (val: boolean) => void;
}

export const ManifestTable: React.FC<ManifestTableProps> = ({
  items,
  onUpdateItem,
  onAddItem,
  onDeleteItem,
  onPackOrder,
  packingLoading,
  applyUncertaintyMargin,
  setApplyUncertaintyMargin,
}) => {
  const handleDimensionChange = (
    index: number,
    field: "length_mm" | "width_mm" | "height_mm",
    val: number
  ) => {
    const item = items[index];
    onUpdateItem(index, {
      ...item,
      dimensions_mm: {
        ...item.dimensions_mm,
        [field]: Math.max(10, val),
      },
      // If user manually updates height on a review item, mark review as completed
      uncertainty_info: item.uncertainty_info
        ? { ...item.uncertainty_info, requires_user_review: false }
        : undefined,
    });
  };

  const handleWeightChange = (index: number, val: number) => {
    const item = items[index];
    onUpdateItem(index, {
      ...item,
      weight_g: Math.max(1, val),
      weight_assumed: false,
    });
  };

  const handleUprightToggle = (index: number, checked: boolean) => {
    const item = items[index];
    const allowed: RotationCode[] = checked
      ? ["LWH", "WLH"]
      : ["LWH", "WLH", "LHW", "HLW", "WHL", "HWL"];
    onUpdateItem(index, {
      ...item,
      keep_upright: checked,
      allowed_rotations: allowed,
    });
  };

  return (
    <div className="card manifest-card">
      <div className="card-header">
        <div className="manifest-header-title">
          <h2>2. Detected Items Manifest & Verification</h2>
          <span className="badge badge-accent">{items.length} Items</span>
        </div>

        <button className="btn btn-sm btn-outline-cyan" onClick={onAddItem} title="Add an uncaptured item manually">
          + Add Manual Item
        </button>
      </div>

      <p className="card-desc">
        Review detected 3D bounding dimensions and AI handling flags. Items with high measurement uncertainty or assumed weight are highlighted for 1-click confirmation before cartonization.
      </p>

      <div className="table-responsive">
        <table className="manifest-table">
          <thead>
            <tr>
              <th>Color</th>
              <th>Item Name</th>
              <th>L × W × H (mm)</th>
              <th>Weight (g)</th>
              <th>Keep Upright</th>
              <th>Fragility</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => {
              const isReviewNeeded =
                item.uncertainty_info?.requires_user_review ||
                (item.uncertainty_info?.height_sigma_mm || 0) > 8;

              return (
                <tr key={item.item_id} className={isReviewNeeded ? "row-review-highlight" : ""}>
                  <td>
                    <span
                      className="color-dot"
                      style={{ backgroundColor: item.display_color_hex }}
                    />
                  </td>
                  <td>
                    <div className="item-title">{item.display_name}</div>
                    <div className="item-meta-badges">
                      <span className="item-id">{item.item_id}</span>
                      {isReviewNeeded ? (
                        <span className="badge badge-warning-pulse" title="Height measured via aspect prior fallback">
                          ⚠️ Review Height (±{item.uncertainty_info?.height_sigma_mm}mm)
                        </span>
                      ) : (
                        <span className="badge badge-calibrated" title="High dual-view confidence">
                          ✓ Calibrated (±{item.safety_margin_mm}mm)
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <div className="dim-inputs">
                      <input
                        type="number"
                        value={item.dimensions_mm.length_mm}
                        onChange={(e) =>
                          handleDimensionChange(idx, "length_mm", parseInt(e.target.value) || 0)
                        }
                        title="Length (mm)"
                      />
                      <span>×</span>
                      <input
                        type="number"
                        value={item.dimensions_mm.width_mm}
                        onChange={(e) =>
                          handleDimensionChange(idx, "width_mm", parseInt(e.target.value) || 0)
                        }
                        title="Width (mm)"
                      />
                      <span>×</span>
                      <input
                        type="number"
                        className={isReviewNeeded ? "input-review-alert" : ""}
                        value={item.dimensions_mm.height_mm}
                        onChange={(e) =>
                          handleDimensionChange(idx, "height_mm", parseInt(e.target.value) || 0)
                        }
                        title="Height (mm) - Review required"
                      />
                    </div>
                  </td>
                  <td>
                    <div className="weight-cell">
                      <input
                        type="number"
                        value={item.weight_g || ""}
                        placeholder="Est. 450"
                        onChange={(e) =>
                          handleWeightChange(idx, parseInt(e.target.value) || 0)
                        }
                        title="Weight in grams"
                      />
                      {item.weight_assumed && (
                        <span className="badge badge-warning" title="Density fallback estimate">
                          Assumed
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <label className="toggle-switch" title="Lock upright orientation (LWH, WLH only)">
                      <input
                        type="checkbox"
                        checked={item.keep_upright}
                        onChange={(e) => handleUprightToggle(idx, e.target.checked)}
                      />
                      <span className="toggle-slider"></span>
                    </label>
                  </td>
                  <td>
                    <select
                      value={item.fragility_class}
                      onChange={(e) =>
                        onUpdateItem(idx, {
                          ...item,
                          fragility_class: e.target.value as any,
                          stackable: e.target.value !== "high",
                          max_top_load_g: e.target.value === "high" ? 0 : 3000,
                        })
                      }
                      className="select-fragility"
                    >
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">High (Fragile)</option>
                    </select>
                  </td>
                  <td>
                    <button
                      className="btn-icon-delete"
                      onClick={() => onDeleteItem(idx)}
                      title="Remove item from manifest"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Action Footer: Margin checkbox & Optimize button */}
      <div className="manifest-footer">
        <label className="checkbox-margin-setting" title="Expands dimensions by +5mm to guarantee fit against measurement error">
          <input
            type="checkbox"
            checked={applyUncertaintyMargin}
            onChange={(e) => setApplyUncertaintyMargin(e.target.checked)}
          />
          <span>Include Measurement Uncertainty Safety Margin (+5mm)</span>
        </label>

        <button
          className="btn btn-success btn-lg"
          onClick={onPackOrder}
          disabled={packingLoading || items.length === 0}
        >
          {packingLoading ? "Optimizing Packing & Cost..." : "Optimize Carton & Pack (CP-SAT)"}
        </button>
      </div>
    </div>
  );
};
