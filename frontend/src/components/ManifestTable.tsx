import React from "react";
import { PackableItem, RotationCode } from "../types/contract";
import { needsMeasurementReview } from "../utils/review";

export interface ExtendedPackableItem extends PackableItem {
  crop_url?: string | null;
  review_acknowledged?: boolean;
  provenance_source?: "AI-Extracted" | "Default-Safe";
  uncertainty_info?: {
    height_sigma_mm: number;
    requires_user_review: boolean;
  };
}

interface ManifestTableProps {
  items: ExtendedPackableItem[];
  onUpdateItem: (index: number, updated: ExtendedPackableItem) => void;
  onConfirmItem: (index: number) => void;
  onAddItem: () => void;
  onDeleteItem: (index: number) => void;
  onPackOrder: () => void;
  packingLoading: boolean;
  applyUncertaintyMargin: boolean;
  setApplyUncertaintyMargin: (val: boolean) => void;
}

type DimField = "length_mm" | "width_mm" | "height_mm";

export const ManifestTable: React.FC<ManifestTableProps> = ({
  items,
  onUpdateItem,
  onConfirmItem,
  onAddItem,
  onDeleteItem,
  onPackOrder,
  packingLoading,
  applyUncertaintyMargin,
  setApplyUncertaintyMargin,
}) => {
  const handleNameChange = (index: number, newName: string) => {
    onUpdateItem(index, {
      ...items[index],
      display_name: newName,
    });
  };

  const handleDimensionChange = (index: number, field: DimField, val: number) => {
    const item = items[index];
    onUpdateItem(index, {
      ...item,
      dimensions_mm: { ...item.dimensions_mm, [field]: Math.max(0, val) },
      // Any new edit requires an explicit acknowledgement; never silently clear provenance.
      review_acknowledged: false,
    });
  };

  const handleDimensionBlur = (index: number, field: DimField) => {
    const item = items[index];
    if (item.dimensions_mm[field] < 10) {
      onUpdateItem(index, {
        ...item,
        dimensions_mm: { ...item.dimensions_mm, [field]: 10 },
      });
    }
  };

  const handleWeightChange = (index: number, val: number) => {
    onUpdateItem(index, {
      ...items[index],
      weight_g: val > 0 ? val : null,
      weight_assumed: false,
    });
  };

  const handleWeightBlur = (index: number) => {
    const item = items[index];
    if (item.weight_g !== null && item.weight_g < 1) {
      onUpdateItem(index, { ...item, weight_g: 1, weight_assumed: false });
    }
  };

  const handleUprightToggle = (index: number, checked: boolean) => {
    const allowed: RotationCode[] = checked
      ? ["LWH", "WLH"]
      : ["LWH", "WLH", "LHW", "HLW", "WHL", "HWL"];
    onUpdateItem(index, { ...items[index], keep_upright: checked, allowed_rotations: allowed });
  };

  const reviewCount = items.filter(needsMeasurementReview).length;

  const dimInput = (item: ExtendedPackableItem, idx: number, field: DimField, warn = false) => (
    <input
      type="number"
      min={10}
      className={`num-input ${warn ? "is-warn" : ""}`}
      value={item.dimensions_mm[field] || ""}
      onChange={(e) => handleDimensionChange(idx, field, parseInt(e.target.value, 10) || 0)}
      onBlur={() => handleDimensionBlur(idx, field)}
    />
  );

  return (
    <section className="panel">
      <header className="panel-head">
        <h2>
          Items <span className="muted">{items.length}</span>
        </h2>
        {reviewCount > 0 && (
          <span className="hint-warn">{reviewCount} need height check</span>
        )}
      </header>

      <div className="table-scroll-container">
        <table className="items">
        <thead>
          <tr>
            <th>Item</th>
            <th>L × W × H (mm)</th>
            <th>Weight (g)</th>
            <th className="center">Upright</th>
            <th>Fragility</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((item, idx) => {
            const review = needsMeasurementReview(item);
            const normalizedFragility =
              item.fragility_class === "unknown" ? "low" : item.fragility_class;
            return (
              <tr key={item.item_id}>
                <td>
                  <div className="item-name-cell">
                    {item.crop_url ? (
                      <img
                        src={item.crop_url}
                        alt={item.display_name}
                        className="item-crop-thumb"
                        onError={(e) => {
                          (e.currentTarget as HTMLImageElement).style.display = "none";
                        }}
                      />
                    ) : (
                      <span
                        className="dot"
                        style={{ backgroundColor: item.display_color_hex }}
                      />
                    )}
                    <div className="item-name-stack">
                      <input
                        type="text"
                        className="name-input"
                        value={item.display_name}
                        title={`#${idx + 1} (${item.item_id}) — Click to rename`}
                        onChange={(e) => handleNameChange(idx, e.target.value)}
                      />
                      <span className="item-sub-meta muted">
                        #{idx + 1} ({item.item_id})
                        {item.provenance_source && (
                          <span
                            className={`prov-tag ${
                              item.provenance_source === "AI-Extracted" ? "is-ai" : "is-safe"
                            }`}
                          >
                            {item.provenance_source === "AI-Extracted" ? "AI" : "Safe"}
                          </span>
                        )}
                      </span>
                    </div>
                  </div>
                </td>
                <td>
                  <div className="dims">
                    {dimInput(item, idx, "length_mm")}
                    {dimInput(item, idx, "width_mm")}
                    <span
                      title={
                        review
                          ? `Height uncertain (±${item.uncertainty_info?.height_sigma_mm} mm). Please verify.`
                          : undefined
                      }
                    >
                      {dimInput(item, idx, "height_mm", review)}
                    </span>
                  </div>
                  {review && (
                    <button type="button" className="btn-link confirm-measurement" onClick={() => onConfirmItem(idx)}
                      aria-label={`Confirm dimensions for ${item.display_name}`}>
                      Confirm dimensions
                    </button>
                  )}
                </td>
                <td>
                  <input
                    type="number"
                    min={1}
                    className={`num-input wide ${item.weight_assumed ? "is-soft" : ""}`}
                    value={item.weight_g ?? ""}
                    placeholder="—"
                    title={
                      item.weight_g === null
                        ? "Weight unobservable from photo (conservative fallback used during packing)"
                        : item.weight_assumed
                        ? "Estimated weight"
                        : "Verified weight"
                    }
                    onChange={(e) => handleWeightChange(idx, parseInt(e.target.value, 10) || 0)}
                    onBlur={() => handleWeightBlur(idx)}
                  />
                </td>
                <td className="center">
                  <input
                    type="checkbox"
                    checked={item.keep_upright}
                    onChange={(e) => handleUprightToggle(idx, e.target.checked)}
                  />
                </td>
                <td>
                  <select
                    className="select"
                    value={normalizedFragility}
                    onChange={(e) => {
                      const nextClass = e.target.value as PackableItem["fragility_class"];
                      onUpdateItem(idx, {
                        ...item,
                        fragility_class: nextClass,
                        stackable: nextClass !== "high" && item.stackable,
                        max_top_load_g: nextClass === "high" ? 0 : 3000,
                      });
                    }}
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </td>
                <td className="right">
                  <button
                    type="button"
                    className="row-delete"
                    onClick={() => onDeleteItem(idx)}
                    aria-label="Remove item"
                  >
                    ×
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>

      <footer className="panel-foot">
        <button type="button" className="btn-link" onClick={onAddItem}>
          + Add item
        </button>
        <label className="check" title="Adds +5 mm to each item to absorb measurement error">
          <input
            type="checkbox"
            checked={applyUncertaintyMargin}
            onChange={(e) => setApplyUncertaintyMargin(e.target.checked)}
          />
          Safety margin
        </label>
        {reviewCount > 0 && <span className="hint-warn" role="status">Confirm {reviewCount} flagged item(s) before packing.</span>}
        <button
          type="button"
          className="btn btn-primary"
          onClick={onPackOrder}
          disabled={packingLoading || items.length === 0 || reviewCount > 0}
        >
          {packingLoading ? "Packing…" : "Pack"}
        </button>
      </footer>
    </section>
  );
};
