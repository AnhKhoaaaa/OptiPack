import React, { useState } from "react";
import { RotationCode } from "../types/contract";
import { ExtendedPackableItem } from "./ManifestTable";

interface ItemVerificationPanelProps {
  items: ExtendedPackableItem[];
  onUpdateItem: (index: number, updated: ExtendedPackableItem) => void;
  onAddItem: () => void;
  onDeleteItem: (index: number) => void;
  onConfirmAll: () => void;
  onRetake: () => void;
  applyUncertaintyMargin: boolean;
  setApplyUncertaintyMargin: (val: boolean) => void;
}

export const ItemVerificationPanel: React.FC<ItemVerificationPanelProps> = ({
  items,
  onUpdateItem,
  onAddItem,
  onDeleteItem,
  onConfirmAll,
  onRetake,
  applyUncertaintyMargin,
  setApplyUncertaintyMargin,
}) => {
  const [editingNameIndex, setEditingNameIndex] = useState<number | null>(null);

  const handleMaterialSelect = (
    index: number,
    material: "soft_fabric" | "rigid_box" | "glass_ceramic" | "metal_wood" | "other"
  ) => {
    const item = items[index];
    const isFragile = material === "glass_ceramic";
    const updated: ExtendedPackableItem = {
      ...item,
      material_type: material,
      fragility_class: isFragile ? "high" : item.fragility_class === "high" ? "medium" : item.fragility_class,
      stackable: isFragile ? false : item.stackable,
      max_top_load_g: isFragile ? 0 : item.max_top_load_g,
    };
    onUpdateItem(index, updated);
  };

  const handleStackingSelect = (
    index: number,
    stackable: boolean,
    maxTopLoadG: number | null
  ) => {
    const item = items[index];
    onUpdateItem(index, {
      ...item,
      stackable,
      max_top_load_g: maxTopLoadG,
    });
  };

  const handleOrientationSelect = (index: number, keepUpright: boolean) => {
    const item = items[index];
    const allowedRotations: RotationCode[] = keepUpright
      ? ["LWH", "WLH"]
      : ["LWH", "WLH", "LHW", "HLW", "WHL", "HWL"];
    onUpdateItem(index, {
      ...item,
      keep_upright: keepUpright,
      allowed_rotations: allowedRotations,
    });
  };

  const handleWeightTierSelect = (
    index: number,
    tier: "light" | "medium" | "heavy"
  ) => {
    const item = items[index];
    const defaultWeightG = tier === "light" ? 300 : tier === "medium" ? 1000 : 3000;
    onUpdateItem(index, {
      ...item,
      weight_tier: tier,
      weight_g: item.weight_g ?? defaultWeightG,
      weight_assumed: true,
    });
  };

  return (
    <div className="panel item-verification-panel">
      {/* Header */}
      <header className="panel-head">
        <div>
          <h2>Verify Items</h2>
        </div>
        <div className="head-actions">
          <label className="checkbox-label text-xs">
            <input
              type="checkbox"
              checked={applyUncertaintyMargin}
              onChange={(e) => setApplyUncertaintyMargin(e.target.checked)}
            />
            <span>+5mm buffer</span>
          </label>
        </div>
      </header>

      {/* Item Cards List */}
      <div className="verification-cards-list">
        {items.map((item, idx) => {
          const dims = item.dimensions_mm;
          const material = item.material_type || (item.fragility_class === "high" ? "glass_ceramic" : "rigid_box");
          const weightTier = item.weight_tier || (item.weight_g && item.weight_g < 500 ? "light" : item.weight_g && item.weight_g > 2000 ? "heavy" : "medium");

          return (
            <div key={item.item_id || idx} className="verification-item-card">
              {/* Card Top Row: Thumbnail + Name + Dims + Delete */}
              <div className="item-card-header">
                <div className="item-thumb-wrapper">
                  {item.crop_url ? (
                    <img src={item.crop_url} alt={item.display_name} className="item-crop-thumb" />
                  ) : (
                    <div className="item-thumb-placeholder">📦</div>
                  )}
                  <span className="item-index-badge">#{idx + 1}</span>
                </div>

                <div className="item-info-col">
                  {editingNameIndex === idx ? (
                    <input
                      type="text"
                      className="item-name-input"
                      value={item.display_name}
                      autoFocus
                      onBlur={() => setEditingNameIndex(null)}
                      onChange={(e) =>
                        onUpdateItem(idx, { ...item, display_name: e.target.value })
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter") setEditingNameIndex(null);
                      }}
                    />
                  ) : (
                    <div
                      className="item-name-display"
                      onClick={() => setEditingNameIndex(idx)}
                      title="Click to rename"
                    >
                      <strong>{item.display_name}</strong>
                      <span className="edit-icon">✏️</span>
                    </div>
                  )}

                  <div className="item-dims-tag">
                    <span>
                      {dims.length_mm} × {dims.width_mm} × {dims.height_mm} mm
                    </span>
                    {applyUncertaintyMargin && (
                      <span className="margin-tag">+{item.safety_margin_mm || 5}mm</span>
                    )}
                  </div>
                </div>

                <button
                  type="button"
                  className="btn-icon-danger"
                  onClick={() => onDeleteItem(idx)}
                  title="Remove item"
                >
                  ✕
                </button>
              </div>

              {/* Card Interactive Chips Rows */}
              <div className="item-chips-matrix">
                {/* 1. Material */}
                <div className="chip-group-row">
                  <span className="chip-group-label">Material</span>
                  <div className="chips-row">
                    <button
                      type="button"
                      className={`pill-chip ${material === "soft_fabric" ? "is-active" : ""}`}
                      onClick={() => handleMaterialSelect(idx, "soft_fabric")}
                    >
                      Soft
                    </button>
                    <button
                      type="button"
                      className={`pill-chip ${material === "rigid_box" ? "is-active" : ""}`}
                      onClick={() => handleMaterialSelect(idx, "rigid_box")}
                    >
                      Box
                    </button>
                    <button
                      type="button"
                      className={`pill-chip ${material === "glass_ceramic" ? "is-active is-warn" : ""}`}
                      onClick={() => handleMaterialSelect(idx, "glass_ceramic")}
                    >
                      Fragile
                    </button>
                    <button
                      type="button"
                      className={`pill-chip ${material === "metal_wood" ? "is-active" : ""}`}
                      onClick={() => handleMaterialSelect(idx, "metal_wood")}
                    >
                      Wood/Metal
                    </button>
                  </div>
                </div>

                {/* 2. Stackability */}
                <div className="chip-group-row">
                  <span className="chip-group-label">Stacking</span>
                  <div className="chips-row">
                    <button
                      type="button"
                      className={`pill-chip ${item.stackable && (item.max_top_load_g === null || item.max_top_load_g >= 2000) ? "is-active" : ""}`}
                      onClick={() => handleStackingSelect(idx, true, 3000)}
                    >
                      Stackable
                    </button>
                    <button
                      type="button"
                      className={`pill-chip ${item.stackable && item.max_top_load_g !== null && item.max_top_load_g < 2000 && item.max_top_load_g > 0 ? "is-active" : ""}`}
                      onClick={() => handleStackingSelect(idx, true, 1000)}
                    >
                      Light load
                    </button>
                    <button
                      type="button"
                      className={`pill-chip ${!item.stackable || item.max_top_load_g === 0 ? "is-active is-danger" : ""}`}
                      onClick={() => handleStackingSelect(idx, false, 0)}
                    >
                      No stack
                    </button>
                  </div>
                </div>

                {/* 3. Orientation */}
                <div className="chip-group-row">
                  <span className="chip-group-label">Placement</span>
                  <div className="chips-row">
                    <button
                      type="button"
                      className={`pill-chip ${!item.keep_upright ? "is-active" : ""}`}
                      onClick={() => handleOrientationSelect(idx, false)}
                    >
                      Any side
                    </button>
                    <button
                      type="button"
                      className={`pill-chip ${item.keep_upright ? "is-active is-upright" : ""}`}
                      onClick={() => handleOrientationSelect(idx, true)}
                    >
                      Upright
                    </button>
                  </div>
                </div>

                {/* 4. Weight Tier */}
                <div className="chip-group-row">
                  <span className="chip-group-label">Weight</span>
                  <div className="chips-row">
                    <button
                      type="button"
                      className={`pill-chip ${weightTier === "light" ? "is-active" : ""}`}
                      onClick={() => handleWeightTierSelect(idx, "light")}
                    >
                      &lt;0.5 kg
                    </button>
                    <button
                      type="button"
                      className={`pill-chip ${weightTier === "medium" ? "is-active" : ""}`}
                      onClick={() => handleWeightTierSelect(idx, "medium")}
                    >
                      0.5–2 kg
                    </button>
                    <button
                      type="button"
                      className={`pill-chip ${weightTier === "heavy" ? "is-active" : ""}`}
                      onClick={() => handleWeightTierSelect(idx, "heavy")}
                    >
                      &gt;2 kg
                    </button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer & Actions */}
      <footer className="panel-foot verification-foot">
        <button type="button" className="btn btn-secondary" onClick={onRetake}>
          ← Retake
        </button>
        <button type="button" className="btn btn-secondary" onClick={onAddItem}>
          + Add Item
        </button>
        <button
          type="button"
          className="btn btn-primary btn-lg verification-primary-btn"
          onClick={onConfirmAll}
          disabled={items.length === 0}
        >
          Next: Choose Box →
        </button>
      </footer>
    </div>
  );
};
