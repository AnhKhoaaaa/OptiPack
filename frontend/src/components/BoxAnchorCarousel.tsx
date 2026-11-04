import React, { useMemo, useState } from "react";
import { CartonSpec, Dimensions3D } from "../types/contract";
import { ExtendedPackableItem } from "./ManifestTable";
import { STANDARD_CARTON_SPECS } from "./CostScorecard";

interface BoxAnchorCarouselProps {
  items: ExtendedPackableItem[];
  selectedBoxes: CartonSpec[];
  onToggleBoxSelection: (carton: CartonSpec) => void;
  onUpdateBox?: (oldCartonId: string, updated: CartonSpec) => void;
  onProceedToPacking: (selectedCartons: CartonSpec[]) => void;
  onBack: () => void;
}

interface AnchorBoxOption {
  id: string;
  name: string;
  realWorldLabel: string;
  dims: Dimensions3D;
  scaleFactor: number;
  cartonSpec: CartonSpec;
}

export const BoxAnchorCarousel: React.FC<BoxAnchorCarouselProps> = ({
  items,
  selectedBoxes,
  onToggleBoxSelection,
  onUpdateBox,
  onProceedToPacking,
  onBack,
}) => {
  const [activeTab, setActiveTab] = useState<"carousel" | "custom">("carousel");
  const [editingBoxId, setEditingBoxId] = useState<string | null>(null);
  const [customCm, setCustomCm] = useState<{ l: string; w: string; h: string }>({
    l: "30",
    w: "22",
    h: "15",
  });

  // Pick anchor item with largest footprint area (L x W)
  const anchorItem = useMemo(() => {
    if (!items || items.length === 0) return null;
    return [...items].sort((a, b) => {
      const areaA = a.dimensions_mm.length_mm * a.dimensions_mm.width_mm;
      const areaB = b.dimensions_mm.length_mm * b.dimensions_mm.width_mm;
      return areaB - areaA;
    })[0];
  }, [items]);

  // Generate 4 anchor-calibrated cartons based on anchor item footprint
  const anchorBoxes: AnchorBoxOption[] = useMemo(() => {
    if (!anchorItem) return [];
    const aL = anchorItem.dimensions_mm.length_mm;
    const aW = anchorItem.dimensions_mm.width_mm;
    const aH = anchorItem.dimensions_mm.height_mm;

    // Standard catalog mapping
    const boxS = STANDARD_CARTON_SPECS["BOX-S"];
    const boxM = STANDARD_CARTON_SPECS["BOX-M"];
    const boxL = STANDARD_CARTON_SPECS["BOX-L"];
    const boxXL = STANDARD_CARTON_SPECS["BOX-XL"];

    return [
      {
        id: "BOX-S",
        name: "Mailer Box",
        realWorldLabel: "Snug fit for single items",
        dims: {
          length_mm: Math.max(200, Math.round(aL * 1.25)),
          width_mm: Math.max(150, Math.round(aW * 1.25)),
          height_mm: Math.max(100, Math.round(aH * 1.2)),
        },
        scaleFactor: 1.25,
        cartonSpec: {
          carton_id: "BOX-S",
          display_name: boxS?.name || "Small Mailer Box",
          internal_dimensions_mm: { length_mm: 200, width_mm: 150, height_mm: 100 },
          tare_weight_g: 120,
          max_payload_g: 3000,
          box_cost_usd: 0.45,
        },
      },
      {
        id: "BOX-M",
        name: "Medium Box",
        realWorldLabel: "Shoe box size for small orders",
        dims: {
          length_mm: Math.max(300, Math.round(aL * 2.0)),
          width_mm: Math.max(220, Math.round(aW * 1.6)),
          height_mm: Math.max(150, Math.round(aH * 1.5)),
        },
        scaleFactor: 2.0,
        cartonSpec: {
          carton_id: "BOX-M",
          display_name: boxM?.name || "Medium Standard Carton",
          internal_dimensions_mm: { length_mm: 300, width_mm: 220, height_mm: 150 },
          tare_weight_g: 220,
          max_payload_g: 8000,
          box_cost_usd: 0.85,
        },
      },
      {
        id: "BOX-L",
        name: "Large Box",
        realWorldLabel: "Spacious for multi-item orders",
        dims: {
          length_mm: Math.max(400, Math.round(aL * 2.8)),
          width_mm: Math.max(300, Math.round(aW * 2.2)),
          height_mm: Math.max(200, Math.round(aH * 2.0)),
        },
        scaleFactor: 2.8,
        cartonSpec: {
          carton_id: "BOX-L",
          display_name: boxL?.name || "Large E-Commerce Carton",
          internal_dimensions_mm: { length_mm: 400, width_mm: 300, height_mm: 200 },
          tare_weight_g: 450,
          max_payload_g: 15000,
          box_cost_usd: 1.65,
        },
      },
      {
        id: "BOX-XL",
        name: "XL Box",
        realWorldLabel: "Bulk fulfillment master carton",
        dims: {
          length_mm: Math.max(500, Math.round(aL * 3.5)),
          width_mm: Math.max(350, Math.round(aW * 2.6)),
          height_mm: Math.max(250, Math.round(aH * 2.4)),
        },
        scaleFactor: 3.5,
        cartonSpec: {
          carton_id: "BOX-XL",
          display_name: boxXL?.name || "Extra-Large Fulfillment Box",
          internal_dimensions_mm: { length_mm: 500, width_mm: 350, height_mm: 250 },
          tare_weight_g: 750,
          max_payload_g: 20000,
          box_cost_usd: 2.45,
        },
      },
    ];
  }, [anchorItem]);

  // Handle save custom box in cm -> convert to mm (add new or update existing)
  const handleSaveCustomBox = () => {
    const l_cm = Math.max(5, parseFloat(customCm.l) || 30);
    const w_cm = Math.max(5, parseFloat(customCm.w) || 20);
    const h_cm = Math.max(5, parseFloat(customCm.h) || 15);

    const customCarton: CartonSpec = {
      carton_id: `CUSTOM_${Math.round(l_cm)}x${Math.round(w_cm)}x${Math.round(h_cm)}`,
      display_name: `Custom (${l_cm} × ${w_cm} × ${h_cm} cm)`,
      internal_dimensions_mm: {
        length_mm: Math.round(l_cm * 10),
        width_mm: Math.round(w_cm * 10),
        height_mm: Math.round(h_cm * 10),
      },
      tare_weight_g: Math.round(l_cm * w_cm * 0.3),
      max_payload_g: 12000,
      box_cost_usd: 1.1,
    };

    if (editingBoxId) {
      if (onUpdateBox) {
        onUpdateBox(editingBoxId, customCarton);
      } else {
        const oldBox = selectedBoxes.find((b) => b.carton_id === editingBoxId);
        if (oldBox) onToggleBoxSelection(oldBox);
        onToggleBoxSelection(customCarton);
      }
      setEditingBoxId(null);
    } else {
      onToggleBoxSelection(customCarton);
    }

    setCustomCm({ l: "30", w: "22", h: "15" });
  };

  const handleStartEdit = (cb: CartonSpec) => {
    setEditingBoxId(cb.carton_id);
    setCustomCm({
      l: String(cb.internal_dimensions_mm.length_mm / 10),
      w: String(cb.internal_dimensions_mm.width_mm / 10),
      h: String(cb.internal_dimensions_mm.height_mm / 10),
    });
  };

  const handleCancelEdit = () => {
    setEditingBoxId(null);
    setCustomCm({ l: "30", w: "22", h: "15" });
  };

  const handleApplyTemplate = (l: number, w: number, h: number) => {
    setCustomCm({ l: String(l), w: String(w), h: String(h) });
  };

  const isBoxSelected = (cartonId: string) => {
    return selectedBoxes.some((b) => b.carton_id === cartonId);
  };

  const hasSelections = selectedBoxes.length > 0;

  return (
    <div className="panel box-anchor-panel">
      {/* Header */}
      <header className="panel-head">
        <div>
          <h2>Choose Box</h2>
        </div>

        {/* Tab switch */}
        <div className="segmented">
          <button
            type="button"
            className={activeTab === "carousel" ? "is-active" : ""}
            onClick={() => setActiveTab("carousel")}
          >
            Standard
          </button>
          <button
            type="button"
            className={activeTab === "custom" ? "is-active" : ""}
            onClick={() => setActiveTab("custom")}
          >
            Custom (cm)
          </button>
        </div>
      </header>

      {/* Anchor Benchmark Reference Banner */}
      {anchorItem && (
        <div className="anchor-banner">
          <div className="anchor-thumb-mini">
            {anchorItem.crop_url ? (
              <img src={anchorItem.crop_url} alt={anchorItem.display_name} />
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                <line x1="12" y1="22.08" x2="12" y2="12" />
              </svg>
            )}
          </div>
          <div className="anchor-text">
            <span>Largest item reference: </span>
            <strong>{anchorItem.display_name}</strong>
            <span className="muted">
              {" "}
              ({anchorItem.dimensions_mm.length_mm} × {anchorItem.dimensions_mm.width_mm} × {anchorItem.dimensions_mm.height_mm} mm)
            </span>
          </div>
        </div>
      )}

      {/* Tab 1: Horizontal Carousel */}
      {activeTab === "carousel" && (
        <div className="anchor-carousel-wrapper">
          <div className="anchor-carousel-track">
            {anchorBoxes.map((box) => {
              const selected = isBoxSelected(box.cartonSpec.carton_id);
              const dims = box.dims;

              // Compute SVG proportional width & height
              const svgW = 200;
              const svgH = 140;
              // Scale box relative to SVG viewport
              const boxPixelW = Math.min(176, Math.max(96, (dims.length_mm / 450) * 156));
              const boxPixelH = Math.min(108, Math.max(64, (dims.width_mm / 350) * 88));
              const boxX = (svgW - boxPixelW) / 2;
              const boxY = (svgH - boxPixelH) / 2 + 4;

              // Anchor item inside box (fixed bottom-left proportional footprint)
              const aW = Math.min(boxPixelW * 0.78, Math.max(34, (boxPixelW / box.scaleFactor)));
              const aH = Math.min(boxPixelH * 0.78, Math.max(26, (boxPixelH / (box.scaleFactor * 0.8))));
              const ratioPct = anchorItem
                ? Math.min(99, Math.round((anchorItem.dimensions_mm.length_mm / dims.length_mm) * 100))
                : 50;
              const anchorName = anchorItem
                ? (anchorItem.display_name.length > 11
                    ? anchorItem.display_name.slice(0, 10) + "…"
                    : anchorItem.display_name)
                : "Anchor";

              return (
                <div
                  key={box.id}
                  className={`anchor-box-card ${selected ? "is-selected" : ""}`}
                  onClick={() => onToggleBoxSelection(box.cartonSpec)}
                >
                  <div className="card-top">
                    <span className="box-size-tag">{box.cartonSpec.carton_id}</span>
                    <span className="box-dims-label">
                      {dims.length_mm} × {dims.width_mm} × {dims.height_mm} mm
                    </span>
                  </div>

                  {/* 2.5D Spatial Drafting Canvas */}
                  <div className="box-svg-canvas">
                    <svg viewBox={`0 0 ${svgW} ${svgH}`} className="anchor-svg">
                      {/* Subtle background reference grid */}
                      <line x1={boxX} y1={boxY} x2={boxX + boxPixelW} y2={boxY} stroke="rgba(148, 163, 184, 0.2)" strokeWidth={1} strokeDasharray="2 3" />
                      <line x1={boxX} y1={boxY + boxPixelH} x2={boxX + boxPixelW} y2={boxY + boxPixelH} stroke="rgba(148, 163, 184, 0.2)" strokeWidth={1} strokeDasharray="2 3" />
                      
                      {/* Box outline with subtle drafting style */}
                      <rect
                        x={boxX}
                        y={boxY}
                        width={boxPixelW}
                        height={boxPixelH}
                        rx={6}
                        fill="rgba(248, 250, 252, 0.6)"
                        stroke="#94a3b8"
                        strokeWidth={1.2}
                        strokeDasharray="4 3"
                      />

                      {/* Box flap fold crease */}
                      <line
                        x1={boxX}
                        y1={boxY + boxPixelH * 0.45}
                        x2={boxX + boxPixelW}
                        y2={boxY + boxPixelH * 0.45}
                        stroke="#cbd5e1"
                        strokeWidth={1}
                        strokeDasharray="2 2"
                      />

                      {/* Anchor Item 2.5D Isometric Top Bevel */}
                      <polygon
                        points={`${boxX + 5},${boxY + boxPixelH - aH - 3} ${boxX + 9},${boxY + boxPixelH - aH - 7} ${boxX + aW + 9},${boxY + boxPixelH - aH - 7} ${boxX + aW + 5},${boxY + boxPixelH - aH - 3}`}
                        fill="rgba(0, 113, 227, 0.35)"
                        stroke="#0071e3"
                        strokeWidth={1}
                      />
                      {/* Anchor item 2.5D Isometric Right Bevel */}
                      <polygon
                        points={`${boxX + aW + 5},${boxY + boxPixelH - aH - 3} ${boxX + aW + 9},${boxY + boxPixelH - aH - 7} ${boxX + aW + 9},${boxY + boxPixelH - 7} ${boxX + aW + 5},${boxY + boxPixelH - 3}`}
                        fill="rgba(0, 113, 227, 0.25)"
                        stroke="#0071e3"
                        strokeWidth={1}
                      />
                      {/* Anchor item footprint front face */}
                      <rect
                        x={boxX + 5}
                        y={boxY + boxPixelH - aH - 3}
                        width={aW}
                        height={aH}
                        rx={3}
                        fill="rgba(0, 113, 227, 0.18)"
                        stroke="#0071e3"
                        strokeWidth={1.2}
                      />
                      {/* Label inside anchor item */}
                      <text
                        x={boxX + 9}
                        y={boxY + boxPixelH - 7}
                        fill="#0071e3"
                        fontSize={9.5}
                        fontWeight="600"
                        fontFamily="var(--mono, monospace)"
                      >
                        {anchorName}
                      </text>
                    </svg>

                    {/* Proportional Ratio Capsule */}
                    <div className="anchor-ratio-tag">
                      <span>Item occupies <strong>{ratioPct}%</strong> of box length</span>
                    </div>
                  </div>

                  <div className="card-body">
                    <h4>{box.name}</h4>
                    <p className="box-desc muted text-xs">{box.realWorldLabel}</p>
                  </div>

                  <div className="card-foot">
                    <button
                      type="button"
                      className={`btn btn-sm box-select-btn ${selected ? "btn-primary" : "btn-secondary"}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleBoxSelection(box.cartonSpec);
                      }}
                    >
                      {selected ? (
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                          <span>Selected</span>
                        </span>
                      ) : (
                        <span>Select Box</span>
                      )}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Tab 2: Custom Box in CM */}
      {activeTab === "custom" && (
        <div className="custom-box-tab-content">
          {/* Custom Box Input Form Card */}
          <div className="custom-box-editor-card">
            <div className="custom-editor-header">
              <span className="custom-editor-title">
                {editingBoxId ? "Edit Custom Carton" : "Create Custom Carton"}
              </span>
              <span className="text-xs muted">Inner dimensions in Centimeters (cm)</span>
            </div>

            <div className="custom-box-inputs-row">
              <div className="mac-num-field">
                <span className="mac-num-label">Length</span>
                <div className="mac-input-wrapper">
                  <input
                    type="number"
                    min="5"
                    max="200"
                    className="mac-num-input"
                    value={customCm.l}
                    onChange={(e) => setCustomCm({ ...customCm, l: e.target.value })}
                    aria-label="Length (cm)"
                  />
                  <span className="mac-unit-suffix">cm</span>
                </div>
              </div>

              <span className="mac-dims-mul">×</span>

              <div className="mac-num-field">
                <span className="mac-num-label">Width</span>
                <div className="mac-input-wrapper">
                  <input
                    type="number"
                    min="5"
                    max="200"
                    className="mac-num-input"
                    value={customCm.w}
                    onChange={(e) => setCustomCm({ ...customCm, w: e.target.value })}
                    aria-label="Width (cm)"
                  />
                  <span className="mac-unit-suffix">cm</span>
                </div>
              </div>

              <span className="mac-dims-mul">×</span>

              <div className="mac-num-field">
                <span className="mac-num-label">Height</span>
                <div className="mac-input-wrapper">
                  <input
                    type="number"
                    min="5"
                    max="200"
                    className="mac-num-input"
                    value={customCm.h}
                    onChange={(e) => setCustomCm({ ...customCm, h: e.target.value })}
                    aria-label="Height (cm)"
                  />
                  <span className="mac-unit-suffix">cm</span>
                </div>
              </div>

              <div className="custom-box-actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleSaveCustomBox}
                >
                  {editingBoxId ? "✓ Update Box" : "+ Add Box"}
                </button>
                {editingBoxId && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleCancelEdit}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>

            {/* Quick Templates */}
            <div className="quick-templates-bar">
              <span className="text-xs muted">Quick Presets:</span>
              <div className="quick-templates-chips">
                <button
                  type="button"
                  className="quick-template-chip"
                  onClick={() => handleApplyTemplate(20, 15, 10)}
                >
                  Mailer (20×15×10)
                </button>
                <button
                  type="button"
                  className="quick-template-chip"
                  onClick={() => handleApplyTemplate(30, 22, 15)}
                >
                  Medium (30×22×15)
                </button>
                <button
                  type="button"
                  className="quick-template-chip"
                  onClick={() => handleApplyTemplate(40, 30, 20)}
                >
                  Large (40×30×20)
                </button>
                <button
                  type="button"
                  className="quick-template-chip"
                  onClick={() => handleApplyTemplate(50, 35, 25)}
                >
                  XL (50×35×25)
                </button>
              </div>
            </div>
          </div>

          {/* List of custom cartons added / editable */}
          {selectedBoxes.filter((b) => b.carton_id.startsWith("CUSTOM_")).length > 0 && (
            <div className="custom-cartons-section">
              <span className="custom-section-title">
                Active Custom Cartons ({selectedBoxes.filter((b) => b.carton_id.startsWith("CUSTOM_")).length})
              </span>
              <div className="custom-cartons-grid">
                {selectedBoxes
                  .filter((b) => b.carton_id.startsWith("CUSTOM_"))
                  .map((cb) => {
                    const isEditing = editingBoxId === cb.carton_id;
                    const dimsMm = cb.internal_dimensions_mm;
                    const l_cm = (dimsMm.length_mm / 10).toFixed(0);
                    const w_cm = (dimsMm.width_mm / 10).toFixed(0);
                    const h_cm = (dimsMm.height_mm / 10).toFixed(0);

                    return (
                      <div
                        key={cb.carton_id}
                        className={`custom-carton-card ${isEditing ? "is-editing" : ""}`}
                      >
                        <div className="custom-carton-left">
                          <span className="custom-box-icon">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                              <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                              <line x1="12" y1="22.08" x2="12" y2="12" />
                            </svg>
                          </span>
                          <div>
                            <strong>{l_cm} × {w_cm} × {h_cm} cm</strong>
                            <span className="custom-carton-sub">
                              ({dimsMm.length_mm} × {dimsMm.width_mm} × {dimsMm.height_mm} mm)
                            </span>
                          </div>
                        </div>

                        <div className="custom-carton-actions">
                          <button
                            type="button"
                            className="btn btn-secondary btn-xs"
                            onClick={() => handleStartEdit(cb)}
                            title="Edit carton dimensions"
                            style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                          >
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>
                            <span>Edit</span>
                          </button>
                          <button
                            type="button"
                            className="item-card-delete"
                            onClick={() => onToggleBoxSelection(cb)}
                            title="Remove custom box"
                            aria-label="Remove custom box"
                          >
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                          </button>
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Footer Navigation */}
      <footer className="panel-foot box-anchor-foot">
        <button type="button" className="btn btn-secondary" onClick={onBack}>
          ← Back
        </button>

        <div className="selection-summary text-xs muted">
          {hasSelections ? (
            <span>
              <strong>{selectedBoxes.length}</strong> box{selectedBoxes.length > 1 ? "es" : ""} selected
            </span>
          ) : (
            <span>Auto-select optimal box</span>
          )}
        </div>

        <button
          type="button"
          className="btn btn-primary btn-lg box-anchor-proceed-btn"
          onClick={() => onProceedToPacking(selectedBoxes)}
        >
          {hasSelections
            ? `Pack in ${selectedBoxes.length} Box${selectedBoxes.length > 1 ? "es" : ""} →`
            : "Find Best Box →"}
        </button>
      </footer>
    </div>
  );
};
