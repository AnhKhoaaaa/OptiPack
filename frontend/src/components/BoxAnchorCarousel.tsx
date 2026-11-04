import React, { useMemo, useState } from "react";
import { CartonSpec, Dimensions3D } from "../types/contract";
import { ExtendedPackableItem } from "./ManifestTable";
import { STANDARD_CARTON_SPECS } from "./CostScorecard";

interface BoxAnchorCarouselProps {
  items: ExtendedPackableItem[];
  selectedBoxes: CartonSpec[];
  onToggleBoxSelection: (carton: CartonSpec) => void;
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
  onProceedToPacking,
  onBack,
}) => {
  const [activeTab, setActiveTab] = useState<"carousel" | "custom">("carousel");
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

  // Handle custom box in cm -> convert to mm
  const handleAddCustomBox = () => {
    const l_cm = parseFloat(customCm.l) || 30;
    const w_cm = parseFloat(customCm.w) || 20;
    const h_cm = parseFloat(customCm.h) || 15;

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

    onToggleBoxSelection(customCarton);
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
              <span>📦</span>
            )}
          </div>
          <div className="anchor-text">
            <span>Reference: </span>
            <strong>{anchorItem.display_name}</strong>
            <span className="muted">
              {" "}
              ({anchorItem.dimensions_mm.length_mm}×{anchorItem.dimensions_mm.width_mm}×{anchorItem.dimensions_mm.height_mm} mm)
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
              const boxPixelW = Math.min(180, Math.max(90, (dims.length_mm / 450) * 160));
              const boxPixelH = Math.min(110, Math.max(60, (dims.width_mm / 350) * 90));
              const boxX = (svgW - boxPixelW) / 2;
              const boxY = (svgH - boxPixelH) / 2;

              // Anchor item inside box (fixed bottom-left proportional footprint)
              const aW = Math.min(boxPixelW * 0.75, Math.max(30, (boxPixelW / box.scaleFactor)));
              const aH = Math.min(boxPixelH * 0.75, Math.max(25, (boxPixelH / (box.scaleFactor * 0.8))));

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

                  {/* 2.5D SVG Projection Diagram */}
                  <div className="box-svg-canvas">
                    <svg viewBox={`0 0 ${svgW} ${svgH}`} className="anchor-svg">
                      {/* Box outline */}
                      <rect
                        x={boxX}
                        y={boxY}
                        width={boxPixelW}
                        height={boxPixelH}
                        rx={6}
                        fill="#f8fafc"
                        stroke="#94a3b8"
                        strokeWidth={1.5}
                        strokeDasharray="4 3"
                      />
                      {/* Box fold flap accents */}
                      <line
                        x1={boxX}
                        y1={boxY + boxPixelH / 2}
                        x2={boxX + boxPixelW}
                        y2={boxY + boxPixelH / 2}
                        stroke="#cbd5e1"
                        strokeWidth={1}
                        strokeDasharray="2 2"
                      />
                      {/* Anchor item footprint inside bottom-left */}
                      <rect
                        x={boxX + 4}
                        y={boxY + boxPixelH - aH - 4}
                        width={aW}
                        height={aH}
                        rx={4}
                        fill="#0071e3"
                        fillOpacity={0.85}
                        stroke="#005bb5"
                        strokeWidth={1}
                      />
                      {/* Label inside anchor item */}
                      <text
                        x={boxX + 8}
                        y={boxY + boxPixelH - 8}
                        fill="#ffffff"
                        fontSize={10}
                        fontWeight="600"
                        fontFamily="sans-serif"
                      >
                        Anchor
                      </text>
                    </svg>
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
                      {selected ? "✓ Selected" : "+ Select Box"}
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
          <p className="text-xs muted" style={{ marginBottom: 12 }}>
            Enter inner carton dimensions in <strong>Centimeters (cm)</strong>. System automatically
            converts to millimeters for exact CP-SAT packing.
          </p>

          <div className="custom-cm-inputs">
            <div className="cm-field">
              <label>Length (cm)</label>
              <input
                type="number"
                min="5"
                max="150"
                value={customCm.l}
                onChange={(e) => setCustomCm({ ...customCm, l: e.target.value })}
              />
            </div>
            <span className="cm-sep">×</span>
            <div className="cm-field">
              <label>Width (cm)</label>
              <input
                type="number"
                min="5"
                max="150"
                value={customCm.w}
                onChange={(e) => setCustomCm({ ...customCm, w: e.target.value })}
              />
            </div>
            <span className="cm-sep">×</span>
            <div className="cm-field">
              <label>Height (cm)</label>
              <input
                type="number"
                min="5"
                max="150"
                value={customCm.h}
                onChange={(e) => setCustomCm({ ...customCm, h: e.target.value })}
              />
            </div>

            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleAddCustomBox}
              style={{ alignSelf: "flex-end" }}
            >
              + Add Custom Carton
            </button>
          </div>

          {/* List of custom cartons added */}
          {selectedBoxes.filter((b) => b.carton_id.startsWith("CUSTOM_")).length > 0 && (
            <div className="custom-selected-list" style={{ marginTop: 14 }}>
              <span className="text-xs muted">Added Custom Cartons:</span>
              <div className="custom-chips-row" style={{ display: "flex", gap: 8, marginTop: 6 }}>
                {selectedBoxes
                  .filter((b) => b.carton_id.startsWith("CUSTOM_"))
                  .map((cb) => (
                    <div key={cb.carton_id} className="pill-chip is-active">
                      <span>{cb.display_name}</span>
                      <button
                        type="button"
                        onClick={() => onToggleBoxSelection(cb)}
                        className="chip-remove"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
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
