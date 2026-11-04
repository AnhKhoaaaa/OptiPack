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

  const handleDimensionChange = (
    index: number,
    field: "length_mm" | "width_mm" | "height_mm",
    val: number
  ) => {
    const item = items[index];
    const newDims = {
      ...item.dimensions_mm,
      [field]: Math.max(0, val),
    };
    onUpdateItem(index, {
      ...item,
      dimensions_mm: newDims,
    });
  };

  const handleDimensionBlur = (
    index: number,
    field: "length_mm" | "width_mm" | "height_mm"
  ) => {
    const item = items[index];
    if ((item.dimensions_mm[field] || 0) < 5) {
      onUpdateItem(index, {
        ...item,
        dimensions_mm: {
          ...item.dimensions_mm,
          [field]: 10,
        },
      });
    }
  };

  const handleMaterialSelect = (
    index: number,
    material: "soft_fabric" | "rigid_box" | "glass_ceramic" | "metal_wood" | "plastic" | "other"
  ) => {
    const item = items[index];
    const isGlass = material === "glass_ceramic";
    // Glass items automatically default to high fragility and no stacking
    const newFragility = isGlass ? "high" : item.fragility_class === "high" ? "medium" : item.fragility_class;
    const isStackable = newFragility !== "high";
    const maxTopLoad = newFragility === "high" ? 0 : newFragility === "medium" ? 1000 : 3000;
    const updated: ExtendedPackableItem = {
      ...item,
      material_type: material,
      fragility_class: newFragility,
      stackable: isStackable,
      max_top_load_g: maxTopLoad,
    };
    onUpdateItem(index, updated);
  };

  const handleFragilitySelect = (
    index: number,
    fragility: "low" | "medium" | "high"
  ) => {
    const item = items[index];
    // Automatically infer stackability based on fragility level:
    // - High: Fragile contents; no items can be stacked on top (stackable = false, max_top_load_g = 0)
    // - Medium: Semi-fragile or moderate strength; light load allowed (stackable = true, max_top_load_g = 1000g)
    // - Low: Sturdy; robust load-bearing (stackable = true, max_top_load_g = 3000g)
    const isStackable = fragility !== "high";
    const maxTopLoad = fragility === "high" ? 0 : fragility === "medium" ? 1000 : 3000;
    const updated: ExtendedPackableItem = {
      ...item,
      fragility_class: fragility,
      stackable: isStackable,
      max_top_load_g: maxTopLoad,
    };
    onUpdateItem(index, updated);
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
          const fragility = item.fragility_class === "high" ? "high" : item.fragility_class === "low" ? "low" : "medium";
          const weightTier = item.weight_tier || (item.weight_g && item.weight_g < 500 ? "light" : item.weight_g && item.weight_g > 2000 ? "heavy" : "medium");

          return (
            <div key={item.item_id || idx} className="verification-item-card">
              {/* Card Top Row: Thumbnail + Name + Dims + Delete */}
              <div className="item-card-header">
                <div className="item-thumb-wrapper">
                  {item.crop_url ? (
                    <img src={item.crop_url} alt={item.display_name} className="item-crop-thumb" />
                  ) : (
                    <div className="item-thumb-placeholder">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="cube-placeholder-svg">
                        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                        <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                        <line x1="12" y1="22.08" x2="12" y2="12" />
                      </svg>
                    </div>
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
                      <span className="edit-icon">
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>
                      </span>
                    </div>
                  )}

                  <div className="item-dims-editor">
                    <div className="dim-inputs-box">
                      <div className="dim-field">
                        <span className="dim-field-label">L</span>
                        <input
                          type="number"
                          min={5}
                          max={2000}
                          className="dim-num-input"
                          value={dims.length_mm || ""}
                          onChange={(e) =>
                            handleDimensionChange(idx, "length_mm", parseInt(e.target.value, 10) || 0)
                          }
                          onBlur={() => handleDimensionBlur(idx, "length_mm")}
                          aria-label="Length (mm)"
                          title="Length (mm)"
                        />
                      </div>
                      <span className="dim-sep">×</span>
                      <div className="dim-field">
                        <span className="dim-field-label">W</span>
                        <input
                          type="number"
                          min={5}
                          max={2000}
                          className="dim-num-input"
                          value={dims.width_mm || ""}
                          onChange={(e) =>
                            handleDimensionChange(idx, "width_mm", parseInt(e.target.value, 10) || 0)
                          }
                          onBlur={() => handleDimensionBlur(idx, "width_mm")}
                          aria-label="Width (mm)"
                          title="Width (mm)"
                        />
                      </div>
                      <span className="dim-sep">×</span>
                      <div className="dim-field">
                        <span className="dim-field-label">H</span>
                        <input
                          type="number"
                          min={5}
                          max={2000}
                          className="dim-num-input"
                          value={dims.height_mm || ""}
                          onChange={(e) =>
                            handleDimensionChange(idx, "height_mm", parseInt(e.target.value, 10) || 0)
                          }
                          onBlur={() => handleDimensionBlur(idx, "height_mm")}
                          aria-label="Height (mm)"
                          title="Height (mm)"
                        />
                      </div>
                      <span className="dim-unit">mm</span>
                    </div>
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
                  aria-label="Remove item"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
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
                      className={`pill-chip ${material === "rigid_box" ? "is-active" : ""}`}
                      onClick={() => handleMaterialSelect(idx, "rigid_box")}
                    >
                      Box / Paper
                    </button>
                    <button
                      type="button"
                      className={`pill-chip ${material === "plastic" ? "is-active" : ""}`}
                      onClick={() => handleMaterialSelect(idx, "plastic")}
                    >
                      Plastic
                    </button>
                    <button
                      type="button"
                      className={`pill-chip ${material === "soft_fabric" ? "is-active" : ""}`}
                      onClick={() => handleMaterialSelect(idx, "soft_fabric")}
                    >
                      Fabric
                    </button>
                    <button
                      type="button"
                      className={`pill-chip ${material === "glass_ceramic" ? "is-active" : ""}`}
                      onClick={() => handleMaterialSelect(idx, "glass_ceramic")}
                    >
                      Glass
                    </button>
                    <button
                      type="button"
                      className={`pill-chip ${material === "metal_wood" ? "is-active" : ""}`}
                      onClick={() => handleMaterialSelect(idx, "metal_wood")}
                    >
                      Wood / Metal
                    </button>
                  </div>
                </div>

                {/* 2. Fragility */}
                <div className="chip-group-row">
                  <span className="chip-group-label">Fragility</span>
                  <div className="chips-row">
                    <button
                      type="button"
                      className={`pill-chip ${fragility === "low" ? "is-active" : ""}`}
                      onClick={() => handleFragilitySelect(idx, "low")}
                    >
                      Low
                    </button>
                    <button
                      type="button"
                      className={`pill-chip ${fragility === "medium" ? "is-active is-warn" : ""}`}
                      onClick={() => handleFragilitySelect(idx, "medium")}
                    >
                      Medium
                    </button>
                    <button
                      type="button"
                      className={`pill-chip ${fragility === "high" ? "is-active is-danger" : ""}`}
                      onClick={() => handleFragilitySelect(idx, "high")}
                    >
                      High
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
