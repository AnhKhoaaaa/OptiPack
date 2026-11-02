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

type DimField = "length_mm" | "width_mm" | "height_mm";

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
  const handleDimensionChange = (index: number, field: DimField, val: number) => {
    const item = items[index];
    onUpdateItem(index, {
      ...item,
      dimensions_mm: { ...item.dimensions_mm, [field]: Math.max(0, val) },
      // Manually editing a dimension counts as completing the review
      uncertainty_info: item.uncertainty_info
        ? { ...item.uncertainty_info, requires_user_review: false }
        : undefined,
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
    onUpdateItem(index, { ...items[index], weight_g: Math.max(0, val), weight_assumed: false });
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

  const reviewCount = items.filter((it) => it.uncertainty_info?.requires_user_review).length;

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

      <table className="items">
        <thead>
          <tr>
            <th>Name</th>
            <th>L × W × H (mm)</th>
            <th>Weight (g)</th>
            <th className="center">Upright</th>
            <th>Fragility</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((item, idx) => {
            const review = !!item.uncertainty_info?.requires_user_review;
            return (
              <tr key={item.item_id}>
                <td>
                  <div className="item-name">
                    <span className="dot" style={{ backgroundColor: item.display_color_hex }} />
                    <span className="truncate" title={item.item_id}>
                      {item.display_name}
                    </span>
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
                </td>
                <td>
                  <input
                    type="number"
                    min={1}
                    className={`num-input wide ${item.weight_assumed ? "is-soft" : ""}`}
                    value={item.weight_g || ""}
                    placeholder="—"
                    title={item.weight_assumed ? "Estimated weight" : undefined}
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
                    value={item.fragility_class}
                    onChange={(e) =>
                      onUpdateItem(idx, {
                        ...item,
                        fragility_class: e.target.value as PackableItem["fragility_class"],
                        stackable: e.target.value !== "high",
                        max_top_load_g: e.target.value === "high" ? 0 : 3000,
                      })
                    }
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">Fragile</option>
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
        <button
          type="button"
          className="btn btn-primary"
          onClick={onPackOrder}
          disabled={packingLoading || items.length === 0}
        >
          {packingLoading ? "Packing…" : "Pack"}
        </button>
      </footer>
    </section>
  );
};
