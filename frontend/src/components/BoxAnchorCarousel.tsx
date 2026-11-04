import React, { useMemo, useRef, useState, useEffect } from "react";
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

/**
 * Cartoon 3D Isometric Cardboard Box with Translucent Phantom Item
 * Mathematically proportioned: item dimensions exactly scaled relative to box internal dimensions.
 */
const CartoonBoxVisual: React.FC<{
  boxDims: Dimensions3D;
  anchorItem: ExtendedPackableItem | null;
}> = ({ boxDims, anchorItem }) => {
  const bL = Math.max(50, boxDims.length_mm);
  const bW = Math.max(50, boxDims.width_mm);
  const bH = Math.max(40, boxDims.height_mm);

  const iL = anchorItem?.dimensions_mm.length_mm ?? 0;
  const iW = anchorItem?.dimensions_mm.width_mm ?? 0;
  const iH = anchorItem?.dimensions_mm.height_mm ?? 0;

  const fits = !anchorItem || (iL <= bL && iW <= bW && iH <= bH);
  const volBox = (bL * bW * bH) / 1000;
  const volItem = (iL * iW * iH) / 1000;
  const volPct = Math.min(99, Math.max(1, Math.round((volItem / Math.max(1, volBox)) * 100)));

  // Viewport setup
  const svgW = 280;
  const svgH = 175;
  const cx = 140;
  const cy = 96;

  // Scale box preserving aspect ratio inside canvas
  const diag = Math.sqrt(bL * bL + bW * bW);
  const scaleXY = Math.min(0.56, 108.0 / Math.max(1, diag));
  const scaleZ = Math.min(0.40, 52.0 / Math.max(1, bH));

  const cos30 = 0.866;
  const sin30 = 0.5;

  const pt = (x: number, y: number, z: number): [number, number] => {
    const px = cx + (x - y) * cos30 * scaleXY;
    const py = cy + (x + y) * sin30 * scaleXY - z * scaleZ;
    return [Math.round(px * 10) / 10, Math.round(py * 10) / 10];
  };

  const toPts = (pts: [number, number][]) => pts.map(([x, y]) => `${x},${y}`).join(" ");

  // Box Floor
  const O = pt(0, 0, 0);
  const R0 = pt(bL, 0, 0);
  const L0 = pt(0, bW, 0);
  const F0 = pt(bL, bW, 0);

  // Box Top Rim
  const Tback = pt(0, 0, bH);
  const Tright = pt(bL, 0, bH);
  const Tleft = pt(0, bW, bH);
  const Tfront = pt(bL, bW, bH);

  // Flaps geometry
  const flapH = Math.min(20, bH * 0.3 * scaleZ + 6);
  const flapL = Math.min(22, bL * 0.25 * scaleXY + 5);
  const flapW = Math.min(22, bW * 0.25 * scaleXY + 5);

  const flapBackPts = toPts([
    Tleft,
    [Tleft[0], Tleft[1] - flapH],
    [Tback[0], Tback[1] - flapH],
    Tback,
  ]);

  const flapRightBackPts = toPts([
    Tback,
    [Tback[0] + flapL * cos30, Tback[1] - flapH * 0.6],
    [Tright[0] + flapL * cos30, Tright[1] - flapH * 0.6],
    Tright,
  ]);

  const flapLeftFrontPts = toPts([
    Tleft,
    [Tleft[0] - flapW * cos30, Tleft[1] + flapH * 0.7],
    [Tfront[0] - flapW * cos30, Tfront[1] + flapH * 0.7],
    Tfront,
  ]);

  const flapFrontRightPts = toPts([
    Tfront,
    [Tfront[0] + flapL * cos30 * 0.7, Tfront[1] + flapH * 0.8],
    [Tright[0] + flapL * cos30 * 0.7, Tright[1] + flapH * 0.8],
    Tright,
  ]);

  // Center phantom item on box floor
  const x0 = Math.max(0, (bL - iL) / 2);
  const y0 = Math.max(0, (bW - iW) / 2);

  const Ib0 = pt(x0, y0, 0);
  const Ir0 = pt(x0 + iL, y0, 0);
  const Il0 = pt(x0, y0 + iW, 0);
  const If0 = pt(x0 + iL, y0 + iW, 0);

  const Ibt = pt(x0, y0, iH);
  const Irt = pt(x0 + iL, y0, iH);
  const Ilt = pt(x0, y0 + iW, iH);
  const Ift = pt(x0 + iL, y0 + iW, iH);

  const itemFloorShadow = toPts([Ib0, Ir0, If0, Il0]);
  const itemTopPts = toPts([Ibt, Irt, Ift, Ilt]);
  const itemLeftPts = toPts([Il0, If0, Ift, Ilt]);
  const itemRightPts = toPts([Ir0, If0, Ift, Irt]);

  // Ground drop shadow under box
  const groundShadowPts = toPts([
    [L0[0] - 12, L0[1] + 4],
    [O[0], O[1] + 12],
    [R0[0] + 12, R0[1] + 4],
    [F0[0], F0[1] + 12],
  ]);

  const itemStroke = fits ? "#0071e3" : "#ff453a";
  const itemTopFill = fits ? "rgba(0, 113, 227, 0.52)" : "rgba(255, 69, 58, 0.55)";
  const itemLeftFill = fits ? "rgba(0, 113, 227, 0.38)" : "rgba(255, 69, 58, 0.42)";
  const itemRightFill = fits ? "rgba(0, 113, 227, 0.28)" : "rgba(255, 69, 58, 0.32)";

  return (
    <div className="cartoon-box-container">
      <svg viewBox={`0 0 ${svgW} ${svgH}`} className="cartoon-box-svg" aria-hidden="true">
        <defs>
          <radialGradient id="boxGroundGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(0,0,0,0.15)" />
            <stop offset="100%" stopColor="rgba(0,0,0,0)" />
          </radialGradient>
        </defs>

        {/* 1. Ground contact shadow under cartoon box */}
        <ellipse cx={cx} cy={F0[1] + 4} rx={scaleXY * diag * 0.85 + 10} ry={12} fill="url(#boxGroundGlow)" />
        <polygon points={groundShadowPts} fill="rgba(80, 50, 20, 0.08)" />

        {/* 2. Back Open Flaps (behind interior) */}
        <polygon points={flapBackPts} fill="#dcb382" stroke="#9c6644" strokeWidth="2" strokeLinejoin="round" />
        <line x1={Tleft[0]} y1={Tleft[1]} x2={Tback[0]} y2={Tback[1]} stroke="#b88358" strokeWidth="1.5" strokeDasharray="3 2" />

        <polygon points={flapRightBackPts} fill="#cf9f6e" stroke="#9c6644" strokeWidth="2" strokeLinejoin="round" />
        <line x1={Tback[0]} y1={Tback[1]} x2={Tright[0]} y2={Tright[1]} stroke="#b88358" strokeWidth="1.5" strokeDasharray="3 2" />

        {/* 3. Interior Walls & Floor */}
        {/* Interior Floor */}
        <polygon points={toPts([O, R0, F0, L0])} fill="#c69565" stroke="#a26f43" strokeWidth="1" strokeLinejoin="round" />
        {/* Interior Back-Left Wall */}
        <polygon points={toPts([O, L0, Tleft, Tback])} fill="#dba876" stroke="#b07a4a" strokeWidth="1" strokeLinejoin="round" />
        {/* Interior Back-Right Wall */}
        <polygon points={toPts([O, R0, Tright, Tback])} fill="#ce9965" stroke="#a67243" strokeWidth="1" strokeLinejoin="round" />

        {/* 4. Phantom Item (Bóng mờ vật đặt bên trong) */}
        {anchorItem && (
          <g className="phantom-item-group">
            {/* Contact shadow on box floor */}
            <polygon points={itemFloorShadow} fill="rgba(60, 30, 10, 0.28)" />

            {/* Item 3D Translucent Volume */}
            <polygon points={itemRightPts} fill={itemRightFill} stroke={itemStroke} strokeWidth="1.4" strokeLinejoin="round" />
            <polygon points={itemLeftPts} fill={itemLeftFill} stroke={itemStroke} strokeWidth="1.4" strokeLinejoin="round" />
            <polygon points={itemTopPts} fill={itemTopFill} stroke={itemStroke} strokeWidth="1.6" strokeLinejoin="round" />

            {/* Subtle item ribbon / label indicator */}
            <line x1={Ilt[0]} y1={Ilt[1]} x2={Irt[0]} y2={Irt[1]} stroke={itemStroke} strokeWidth="1" strokeDasharray="2 2" opacity={0.7} />
          </g>
        )}

        {/* 5. Front Walls of Cartoon Box (Frosted translucent kraft so item is visible inside) */}
        {/* Front-Left Face */}
        <polygon
          points={toPts([L0, F0, Tfront, Tleft])}
          fill="rgba(242, 216, 182, 0.72)"
          stroke="#9c6644"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        {/* Front-Right Face */}
        <polygon
          points={toPts([R0, F0, Tfront, Tright])}
          fill="rgba(230, 200, 164, 0.72)"
          stroke="#9c6644"
          strokeWidth="2"
          strokeLinejoin="round"
        />

        {/* Front Center Crease Line */}
        <line x1={F0[0]} y1={F0[1]} x2={Tfront[0]} y2={Tfront[1]} stroke="#9c6644" strokeWidth="2" strokeLinecap="round" />

        {/* 6. Front Open Flaps (Folded down forward) */}
        <polygon points={flapLeftFrontPts} fill="#e5bb87" stroke="#9c6644" strokeWidth="2" strokeLinejoin="round" />
        <line x1={Tleft[0]} y1={Tleft[1]} x2={Tfront[0]} y2={Tfront[1]} stroke="#b88358" strokeWidth="1.5" strokeDasharray="3 2" />

        <polygon points={flapFrontRightPts} fill="#dbae76" stroke="#9c6644" strokeWidth="2" strokeLinejoin="round" />
        <line x1={Tfront[0]} y1={Tfront[1]} x2={Tright[0]} y2={Tright[1]} stroke="#b88358" strokeWidth="1.5" strokeDasharray="3 2" />
      </svg>

      {/* Dynamic Fit Indicator Pill beneath cartoon box */}
      <div className="box-visual-status">
        {fits ? (
          volPct > 70 ? (
            <span className="box-fit-pill is-snug">
              <span className="fit-dot is-amber" />
              <span>Snug fit · <strong>{volPct}%</strong> vol</span>
            </span>
          ) : (
            <span className="box-fit-pill is-comfortable">
              <span className="fit-dot is-blue" />
              <span>Fits comfortably · <strong>{volPct}%</strong> vol</span>
            </span>
          )
        ) : (
          <span className="box-fit-pill is-overflow">
            <span className="fit-dot is-red" />
            <span>Exceeds box dimensions</span>
          </span>
        )}
      </div>
    </div>
  );
};

export const BoxAnchorCarousel: React.FC<BoxAnchorCarouselProps> = ({
  items,
  selectedBoxes,
  onToggleBoxSelection,
  onUpdateBox,
  onProceedToPacking,
  onBack,
}) => {
  const [activeTab, setActiveTab] = useState<"carousel" | "custom">("carousel");
  const [activeCardIndex, setActiveCardIndex] = useState<number>(1); // Default to BOX-M or middle
  const [editingBoxId, setEditingBoxId] = useState<string | null>(null);
  const [customCm, setCustomCm] = useState<{ l: string; w: string; h: string }>({
    l: "30",
    w: "22",
    h: "15",
  });

  const wrapperRef = useRef<HTMLDivElement>(null);

  // Pick anchor item with largest footprint area (L x W)
  const anchorItem = useMemo(() => {
    if (!items || items.length === 0) return null;
    return [...items].sort((a, b) => {
      const areaA = a.dimensions_mm.length_mm * a.dimensions_mm.width_mm;
      const areaB = b.dimensions_mm.length_mm * b.dimensions_mm.width_mm;
      return areaB - areaA;
    })[0];
  }, [items]);

  // Generate 6 anchor cartons from XS to XXL
  const anchorBoxes: AnchorBoxOption[] = useMemo(() => {
    const boxXS = STANDARD_CARTON_SPECS["BOX-XS"];
    const boxS = STANDARD_CARTON_SPECS["BOX-S"];
    const boxM = STANDARD_CARTON_SPECS["BOX-M"];
    const boxL = STANDARD_CARTON_SPECS["BOX-L"];
    const boxXL = STANDARD_CARTON_SPECS["BOX-XL"];
    const boxXXL = STANDARD_CARTON_SPECS["BOX-XXL"];

    return [
      {
        id: "BOX-XS",
        name: "Mini Mailer",
        realWorldLabel: "Small accessories, jewelry & cosmetics",
        dims: { length_mm: 160, width_mm: 110, height_mm: 70 },
        scaleFactor: 1.0,
        cartonSpec: {
          carton_id: "BOX-XS",
          display_name: boxXS?.name || "Mini Mailer Box",
          internal_dimensions_mm: { length_mm: 160, width_mm: 110, height_mm: 70 },
          tare_weight_g: 50,
          max_payload_g: 1500,
          box_cost_usd: 0.30,
        },
      },
      {
        id: "BOX-S",
        name: "Mailer Box",
        realWorldLabel: "Snug fit for single items & books",
        dims: { length_mm: 200, width_mm: 150, height_mm: 100 },
        scaleFactor: 1.25,
        cartonSpec: {
          carton_id: "BOX-S",
          display_name: boxS?.name || "Small Mailer Box",
          internal_dimensions_mm: { length_mm: 200, width_mm: 150, height_mm: 100 },
          tare_weight_g: 85,
          max_payload_g: 3000,
          box_cost_usd: 0.45,
        },
      },
      {
        id: "BOX-M",
        name: "Medium Box",
        realWorldLabel: "Shoe box size for everyday orders",
        dims: { length_mm: 300, width_mm: 220, height_mm: 150 },
        scaleFactor: 2.0,
        cartonSpec: {
          carton_id: "BOX-M",
          display_name: boxM?.name || "Medium Standard Carton",
          internal_dimensions_mm: { length_mm: 300, width_mm: 220, height_mm: 150 },
          tare_weight_g: 160,
          max_payload_g: 8000,
          box_cost_usd: 0.85,
        },
      },
      {
        id: "BOX-L",
        name: "Large Box",
        realWorldLabel: "Spacious for multi-item apparel & sets",
        dims: { length_mm: 400, width_mm: 300, height_mm: 200 },
        scaleFactor: 2.8,
        cartonSpec: {
          carton_id: "BOX-L",
          display_name: boxL?.name || "Large E-Commerce Carton",
          internal_dimensions_mm: { length_mm: 400, width_mm: 300, height_mm: 200 },
          tare_weight_g: 280,
          max_payload_g: 15000,
          box_cost_usd: 1.40,
        },
      },
      {
        id: "BOX-XL",
        name: "XL Box",
        realWorldLabel: "Bulky fulfillment & winter apparel",
        dims: { length_mm: 500, width_mm: 350, height_mm: 250 },
        scaleFactor: 3.5,
        cartonSpec: {
          carton_id: "BOX-XL",
          display_name: boxXL?.name || "Extra-Large Fulfillment Box",
          internal_dimensions_mm: { length_mm: 500, width_mm: 350, height_mm: 250 },
          tare_weight_g: 420,
          max_payload_g: 20000,
          box_cost_usd: 2.10,
        },
      },
      {
        id: "BOX-XXL",
        name: "XXL Master Box",
        realWorldLabel: "Consolidated wholesale master carton",
        dims: { length_mm: 600, width_mm: 400, height_mm: 350 },
        scaleFactor: 4.5,
        cartonSpec: {
          carton_id: "BOX-XXL",
          display_name: boxXXL?.name || "Heavy Bulk Master Carton",
          internal_dimensions_mm: { length_mm: 600, width_mm: 400, height_mm: 350 },
          tare_weight_g: 650,
          max_payload_g: 25000,
          box_cost_usd: 3.20,
        },
      },
    ];
  }, []);

  // Smooth scroll to card index
  const scrollToCard = (index: number) => {
    if (!wrapperRef.current) return;
    const track = wrapperRef.current.firstElementChild as HTMLElement;
    if (!track) return;
    const cards = track.children;
    if (cards[index]) {
      cards[index].scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      setActiveCardIndex(index);
    }
  };

  // Scroll listener to update active pagination dot
  const handleScroll = () => {
    if (!wrapperRef.current) return;
    const scrollLeft = wrapperRef.current.scrollLeft;
    const cardWidth = 330;
    const idx = Math.round(scrollLeft / cardWidth);
    if (idx >= 0 && idx < anchorBoxes.length && idx !== activeCardIndex) {
      setActiveCardIndex(idx);
    }
  };

  const handlePrev = () => {
    const nextIdx = Math.max(0, activeCardIndex - 1);
    scrollToCard(nextIdx);
  };

  const handleNext = () => {
    const nextIdx = Math.min(anchorBoxes.length - 1, activeCardIndex + 1);
    scrollToCard(nextIdx);
  };

  // Handle custom box in cm -> convert to mm
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
            Standard ({anchorBoxes.length})
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

      {/* Tab 1: Select & Swipe Carousel Track */}
      {activeTab === "carousel" && (
        <div className="carousel-experience-wrapper">
          {/* Navigation Controls Bar */}
          <div className="carousel-nav-bar">
            <span className="carousel-guide-hint">
              Swipe or use arrows to compare box options ({activeCardIndex + 1} of {anchorBoxes.length})
            </span>
            <div className="carousel-arrow-buttons">
              <button
                type="button"
                className="carousel-arrow-btn"
                onClick={handlePrev}
                disabled={activeCardIndex === 0}
                aria-label="Previous Box"
                title="Previous Box"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
              </button>
              <button
                type="button"
                className="carousel-arrow-btn"
                onClick={handleNext}
                disabled={activeCardIndex === anchorBoxes.length - 1}
                aria-label="Next Box"
                title="Next Box"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            </div>
          </div>

          {/* Swipe Track */}
          <div className="anchor-carousel-wrapper" ref={wrapperRef} onScroll={handleScroll}>
            <div className="anchor-carousel-track">
              {anchorBoxes.map((box, idx) => {
                const selected = isBoxSelected(box.cartonSpec.carton_id);
                const dims = box.dims;
                const isCenter = idx === activeCardIndex;

                return (
                  <div
                    key={box.id}
                    className={`anchor-box-card ${selected ? "is-selected" : ""} ${isCenter ? "is-focal" : ""}`}
                    onClick={() => {
                      scrollToCard(idx);
                      onToggleBoxSelection(box.cartonSpec);
                    }}
                  >
                    <div className="card-top">
                      <span className="box-size-tag">{box.cartonSpec.carton_id}</span>
                      <span className="box-dims-label">
                        {dims.length_mm} × {dims.width_mm} × {dims.height_mm} mm
                      </span>
                    </div>

                    {/* Cartoon Cardboard Box Illustration */}
                    <div className="box-svg-canvas">
                      <CartoonBoxVisual boxDims={dims} anchorItem={anchorItem} />
                    </div>

                    <div className="card-body">
                      <h4>{box.name}</h4>
                      <p className="box-desc muted text-xs">{box.realWorldLabel}</p>
                      <div className="box-specs-row text-xs muted">
                        <span>Tare: {box.cartonSpec.tare_weight_g}g</span>
                        <span>·</span>
                        <span>Max: {(box.cartonSpec.max_payload_g / 1000).toFixed(1)} kg</span>
                        <span>·</span>
                        <strong className="text-primary">${box.cartonSpec.box_cost_usd.toFixed(2)}</strong>
                      </div>
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

          {/* Dots Pagination Indicator */}
          <div className="carousel-dots-bar">
            {anchorBoxes.map((b, idx) => (
              <button
                key={b.id}
                type="button"
                className={`carousel-dot ${idx === activeCardIndex ? "is-active" : ""}`}
                onClick={() => scrollToCard(idx)}
                aria-label={`Go to ${b.cartonSpec.carton_id}`}
                title={b.cartonSpec.carton_id}
              />
            ))}
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
                  onClick={() => handleApplyTemplate(16, 11, 7)}
                >
                  Mini (16×11×7)
                </button>
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
