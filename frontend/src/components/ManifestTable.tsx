import React from "react";
import { PackableItem, RotationCode } from "../types/contract";

export interface ExtendedPackableItem extends PackableItem {
  uncertainty_info?: {
    height_sigma_mm: number;
    requires_user_review: boolean;
  };
  crop_url?: string | null;
  provenance_source?: "AI-Extracted" | "Default-Safe";
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
        [field]: Math.max(0, val),
      },
      // If user manually updates height on a review item, mark review as completed
      uncertainty_info: item.uncertainty_info
        ? { ...item.uncertainty_info, requires_user_review: false }
        : undefined,
    });
  };

  const handleDimensionBlur = (
    index: number,
    field: "length_mm" | "width_mm" | "height_mm"
  ) => {
    const item = items[index];
    const currentVal = item.dimensions_mm[field];
    if (currentVal < 10) {
      onUpdateItem(index, {
        ...item,
        dimensions_mm: {
          ...item.dimensions_mm,
          [field]: Math.max(10, currentVal),
        },
      });
    }
  };

  const handleWeightChange = (index: number, val: number) => {
    const item = items[index];
    onUpdateItem(index, {
      ...item,
      weight_g: Math.max(0, val),
      weight_assumed: false,
    });
  };

  const handleWeightBlur = (index: number) => {
    const item = items[index];
    if (item.weight_g !== null && item.weight_g < 1) {
      onUpdateItem(index, {
        ...item,
        weight_g: 1,
        weight_assumed: false,
      });
    }
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
              <th>Photo</th>
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
                  <td className="crop-cell">
                    {item.crop_url ? (
                      <div className="crop-thumb-wrapper" title={`Visual crop: ${item.display_name}`}>
                        <img
                          src={item.crop_url}
                          alt={item.display_name}
                          className="item-crop-thumb"
                          onError={(e) => {
                            (e.target as HTMLElement).style.display = "none";
                            const parent = (e.target as HTMLElement).parentElement;
                            if (parent) {
                              const fallback = parent.querySelector(".crop-fallback-icon");
                              if (fallback) (fallback as HTMLElement).style.display = "flex";
                            }
                          }}
                        />
                        <span className="crop-fallback-icon" style={{ display: "none" }}>📦</span>
                      </div>
                    ) : (
                      <div className="crop-thumb-wrapper crop-thumb-empty" title="No visual crop available">
                        <span className="crop-fallback-icon">📦</span>
                      </div>
                    )}
                  </td>
                  <td>
                    <div className="item-title">{item.display_name}</div>
                    <div className="item-meta-badges">
                      <span className="item-id">{item.item_id}</span>
                      <span
                        className={`badge ${
                          item.provenance_source === "AI-Extracted"
                            ? "badge-meta-extracted"
                            : "badge-default-safe"
                        }`}
                        title={
                          item.provenance_source === "AI-Extracted"
                            ? "Extracted by Meta AI vision pipeline"
                            : "Conservative system default (Safe / Uncalibrated)"
                        }
                      >
                        {item.provenance_source || "Default-Safe"}
                      </span>
                      {isReviewNeeded ? (
                        <span className="badge badge-warning-pulse" title="Requires user verification">
                          ⚠️ Requires Review (±{item.uncertainty_info?.height_sigma_mm}mm)
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
                        min="10"
                        max="2000"
                        value={item.dimensions_mm.length_mm}
                        onChange={(e) =>
                          handleDimensionChange(idx, "length_mm", Number(e.target.value))
                        }
                        onBlur={() => handleDimensionBlur(idx, "length_mm")}
                        title="Length in mm"
                      />
                      <span>×</span>
                      <input
                        type="number"
                        min="10"
                        max="2000"
                        value={item.dimensions_mm.width_mm}
                        onChange={(e) =>
                          handleDimensionChange(idx, "width_mm", Number(e.target.value))
                        }
                        onBlur={() => handleDimensionBlur(idx, "width_mm")}
                        title="Width in mm"
                      />
                      <span>×</span>
                      <input
                        type="number"
                        min="10"
                        max="2000"
                        className={isReviewNeeded ? "input-review-alert" : ""}
                        value={item.dimensions_mm.height_mm}
                        onChange={(e) =>
                          handleDimensionChange(idx, "height_mm", Number(e.target.value))
                        }
                        onBlur={() => handleDimensionBlur(idx, "height_mm")}
                        title={
                          isReviewNeeded
                            ? "Review Height: Click or edit to confirm"
                            : "Height in mm"
                        }
                      />
                    </div>
                  </td>
                  <td>
                    <div className="weight-input-group">
                      <input
                        type="number"
                        min="1"
                        max="50000"
                        value={item.weight_g ?? ""}
                        placeholder="Unknown"
                        onChange={(e) =>
                          handleWeightChange(
                            idx,
                            e.target.value === "" ? 0 : Number(e.target.value)
                          )
                        }
                        onBlur={() => handleWeightBlur(idx)}
                      />
                      {item.weight_assumed && (
                        <span
                          className="badge badge-warning"
                          title="Weight inferred from density fallback; confirm if known"
                        >
                          Assumed
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <label className="switch-toggle" title="Lock vertical orientation">
                      <input
                        type="checkbox"
                        checked={item.keep_upright}
                        onChange={(e) => handleUprightToggle(idx, e.target.checked)}
                      />
                      <span className="slider"></span>
                    </label>
                  </td>
                  <td>
                    <span
                      className={`fragility-tag fragility-${item.fragility_class}`}
                      title={`Fragility: ${item.fragility_class.toUpperCase()}`}
                    >
                      {item.fragility_class.toUpperCase()}
                    </span>
                  </td>
                  <td>
                    <button
                      className="btn-icon-delete"
                      onClick={() => onDeleteItem(idx)}
                      title="Remove item"
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

      <div className="manifest-footer">
        <label className="checkbox-margin-setting">
          <input
            type="checkbox"
            checked={applyUncertaintyMargin}
            onChange={(e) => setApplyUncertaintyMargin(e.target.checked)}
          />
          <span>
            Expand box bounding boxes with AI Safety Margin (<strong>+5mm</strong> buffer for tape & carton variation)
          </span>
        </label>

        <button
          className="btn btn-accent btn-full-width btn-pack"
          onClick={onPackOrder}
          disabled={packingLoading || items.length === 0}
        >
          {packingLoading ? "Solving 3D Packing (CP-SAT Solver)..." : "📦 Run 3D Cartonization"}
        </button>
      </div>
    </div>
  );
};
