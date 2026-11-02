import React, { useEffect, useState } from "react";
import { OrderAnalysisResponse, PackingSolutionResponse } from "../types/contract";
import { ExtendedPackableItem } from "./ManifestTable";
import { OptiPackClient } from "../api/optipackClient";
import orderAnalysisSample from "../mocks/orderAnalysisSample.json";
import preset2UncertainReview from "../mocks/preset2UncertainReview.json";
import preset2PackingSolution from "../mocks/preset2PackingSolution.json";
import preset3OrderAnalysis from "../mocks/preset3OrderAnalysis.json";
import preset3MultiCartonSplit from "../mocks/preset3MultiCartonSplit.json";

interface UploadPanelProps {
  onAnalysisLoaded: (
    analysis: OrderAnalysisResponse,
    precomputedSolution?: PackingSolutionResponse
  ) => void;
  loading: boolean;
  setLoading: (l: boolean) => void;
  analysis?: OrderAnalysisResponse | null;
  items?: ExtendedPackableItem[];
}

export const UploadPanel: React.FC<UploadPanelProps> = ({
  onAnalysisLoaded,
  loading,
  setLoading,
  analysis,
  items = [],
}) => {
  const [topFile, setTopFile] = useState<File | null>(null);
  const [obliqueFile, setObliqueFile] = useState<File | null>(null);
  const [topPreview, setTopPreview] = useState<string | null>("/samples/topdown_sample.jpg");
  const [obliquePreview, setObliquePreview] = useState<string | null>("/samples/oblique_sample.jpg");
  const [selectedPreset, setSelectedPreset] = useState<number>(1);
  const [showBoundingBoxes, setShowBoundingBoxes] = useState<boolean>(true);
  const [hoveredItemId, setHoveredItemId] = useState<string | null>(null);

  // Clean up object URLs created via URL.createObjectURL to prevent browser memory leaks
  useEffect(() => {
    return () => {
      if (topPreview && topPreview.startsWith("blob:")) URL.revokeObjectURL(topPreview);
      if (obliquePreview && obliquePreview.startsWith("blob:")) URL.revokeObjectURL(obliquePreview);
    };
  }, [topPreview, obliquePreview]);

  const handleTopFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setTopFile(file);
    if (topPreview && topPreview.startsWith("blob:")) URL.revokeObjectURL(topPreview);
    if (file) {
      setTopPreview(URL.createObjectURL(file));
    } else {
      setTopPreview("/samples/topdown_sample.jpg");
    }
  };

  const handleObliqueFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setObliqueFile(file);
    if (obliquePreview && obliquePreview.startsWith("blob:")) URL.revokeObjectURL(obliquePreview);
    if (file) {
      setObliquePreview(URL.createObjectURL(file));
    } else {
      setObliquePreview("/samples/oblique_sample.jpg");
    }
  };

  const handleLoadPreset = (presetNumber: number) => {
    setSelectedPreset(presetNumber);
    setLoading(true);
    // Keep sample preview active
    setTopPreview("/samples/topdown_sample.jpg");
    setObliquePreview("/samples/oblique_sample.jpg");

    setTimeout(() => {
      if (presetNumber === 1) {
        onAnalysisLoaded(orderAnalysisSample as unknown as OrderAnalysisResponse);
      } else if (presetNumber === 2) {
        onAnalysisLoaded(
          preset2UncertainReview as unknown as OrderAnalysisResponse,
          preset2PackingSolution as unknown as PackingSolutionResponse
        );
      } else if (presetNumber === 3) {
        onAnalysisLoaded(
          preset3OrderAnalysis as unknown as OrderAnalysisResponse,
          preset3MultiCartonSplit as unknown as PackingSolutionResponse
        );
      }
      setLoading(false);
    }, 350);
  };

  const handleUploadAndAnalyze = async () => {
    setLoading(true);
    const formData = new FormData();
    if (topFile) {
      formData.append("top_image", topFile);
    }
    if (obliqueFile) {
      formData.append("oblique_image", obliqueFile);
    }
    formData.append("capture_mode", obliqueFile ? "dual_photo" : "single_top_photo");

    try {
      const data = await OptiPackClient.analyzeOrder(formData);
      onAnalysisLoaded(data);
    } catch (err) {
      console.error("[UploadPanel] Analysis request failed:", err);
      // Fallback to sample data for smooth presentation demo if backend is offline
      onAnalysisLoaded(orderAnalysisSample as unknown as OrderAnalysisResponse);
    } finally {
      setLoading(false);
    }
  };

  // Determine dynamic viewBox for the SVG overlay
  const analysisItems = analysis?.items || [];
  const svgMaxX = Math.max(
    1280,
    ...analysisItems.map((it) => it.visual_evidence?.bbox_2d_px?.[2] || 0)
  );
  const svgMaxY = Math.max(
    960,
    ...analysisItems.map((it) => it.visual_evidence?.bbox_2d_px?.[3] || 0)
  );

  return (
    <div className="card upload-card">
      <div className="card-header">
        <div className="upload-header-title">
          <h2>1. Order Capture & Metrology</h2>
          <span className="badge badge-primary">Step 1 of 3</span>
        </div>
        <span className="badge badge-outline">A4 ArUco Board</span>
      </div>

      <p className="card-desc">
        Capture or upload top-down + oblique images of items on the A4 ArUco calibration sheet, or select a pre-calibrated Demo Preset for zero-camera live demo.
      </p>

      {/* AI Tabletop Inspection Stage (Dropzone with Live Bounding Box Overlay) */}
      <div className="detection-stage-wrapper">
        <div className="stage-header">
          <div className="stage-title">
            <span className="stage-pulse-dot" />
            <strong>Zenith View — AI Detection & Metrology Overlay</strong>
          </div>
          <div className="stage-actions">
            {analysisItems.length > 0 && (
              <button
                type="button"
                className={`btn-pill-small ${showBoundingBoxes ? "active" : ""}`}
                onClick={() => setShowBoundingBoxes(!showBoundingBoxes)}
                title="Toggle AI Bounding Box Overlay"
              >
                {showBoundingBoxes ? "✓ Bounding Boxes (ON)" : "Bounding Boxes (OFF)"}
              </button>
            )}
            <span className="badge badge-accent">
              {analysisItems.length} Objects Detected
            </span>
          </div>
        </div>

        <div className="stage-viewport">
          {topPreview ? (
            <div className="stage-image-container">
              <img
                src={topPreview}
                alt="Tabletop Zenith View"
                className="stage-image"
              />

              {/* Scanning Radar Beam Animation during Analysis */}
              {loading && (
                <div className="scanner-overlay">
                  <div className="scanner-beam" />
                  <div className="scanner-hud-text">
                    <span className="scanner-spinner" />
                    <span>Meta AI Metrology & SAM Auto-Segmentation in Progress...</span>
                  </div>
                </div>
              )}

              {/* 2D Bounding Box SVG Overlay */}
              {showBoundingBoxes && !loading && (
                <svg
                  className="bbox-svg-overlay"
                  viewBox={`0 0 ${svgMaxX} ${svgMaxY}`}
                  preserveAspectRatio="xMidYMid meet"
                >
                  <defs>
                    <filter id="bbox-glow" x="-20%" y="-20%" width="140%" height="140%">
                      <feGaussianBlur stdDeviation="4" result="blur" />
                      <feComposite in="SourceGraphic" in2="blur" operator="over" />
                    </filter>
                  </defs>

                  {analysisItems.map((item, idx) => {
                    const bbox = item.visual_evidence?.bbox_2d_px || [0, 0, 100, 100];
                    const [x1, y1, x2, y2] = bbox;
                    const w = Math.max(10, x2 - x1);
                    const h = Math.max(10, y2 - y1);
                    const color = item.visual_evidence?.display_color_hex || "#38bdf8";
                    const isHovered = hoveredItemId === item.item_id;
                    const isReview =
                      item.measurement_provenance?.requires_user_review ||
                      (item.uncertainty_mm?.height_sigma_mm || 0) > 8;

                    // Match item from manifest if available to show updated dims
                    const manifestItem = items.find((mi) => mi.item_id === item.item_id);
                    const lengthMm = manifestItem?.dimensions_mm.length_mm || item.dimensions_mm.length_mm;
                    const widthMm = manifestItem?.dimensions_mm.width_mm || item.dimensions_mm.width_mm;
                    const heightMm = manifestItem?.dimensions_mm.height_mm || item.dimensions_mm.height_mm;

                    const labelX = x1;
                    const labelY = Math.max(30, y1 - 10);
                    const labelWidth = Math.min(260, Math.max(160, item.display_name.length * 9.5));

                    const cornerLen = Math.min(24, Math.min(w, h) * 0.3);

                    return (
                      <g
                        key={item.item_id}
                        className={`bbox-group ${isHovered ? "bbox-hovered" : ""}`}
                        onMouseEnter={() => setHoveredItemId(item.item_id)}
                        onMouseLeave={() => setHoveredItemId(null)}
                      >
                        {/* Main Bounding Box Rectangle */}
                        <rect
                          x={x1}
                          y={y1}
                          width={w}
                          height={h}
                          rx={6}
                          fill={color}
                          fillOpacity={isHovered ? 0.28 : 0.16}
                          stroke={color}
                          strokeWidth={isHovered ? 3.5 : 2.5}
                          filter={isHovered ? "url(#bbox-glow)" : undefined}
                          className="bbox-rect"
                        />

                        {/* Tech Corner Reticles */}
                        <path
                          d={`M ${x1} ${y1 + cornerLen} L ${x1} ${y1} L ${x1 + cornerLen} ${y1}`}
                          stroke={color}
                          strokeWidth={4}
                          strokeLinecap="round"
                          fill="none"
                        />
                        <path
                          d={`M ${x2 - cornerLen} ${y1} L ${x2} ${y1} L ${x2} ${y1 + cornerLen}`}
                          stroke={color}
                          strokeWidth={4}
                          strokeLinecap="round"
                          fill="none"
                        />
                        <path
                          d={`M ${x1} ${y2 - cornerLen} L ${x1} ${y2} L ${x1 + cornerLen} ${y2}`}
                          stroke={color}
                          strokeWidth={4}
                          strokeLinecap="round"
                          fill="none"
                        />
                        <path
                          d={`M ${x2 - cornerLen} ${y2} L ${x2} ${y2} L ${x2} ${y2 - cornerLen}`}
                          stroke={color}
                          strokeWidth={4}
                          strokeLinecap="round"
                          fill="none"
                        />

                        {/* Item Tag Pill & Label */}
                        <g transform={`translate(${labelX}, ${labelY})`}>
                          <rect
                            x={0}
                            y={-24}
                            width={labelWidth}
                            height={24}
                            rx={5}
                            fill="#0b0f19"
                            stroke={color}
                            strokeWidth={1.5}
                            opacity={0.94}
                          />
                          <circle cx={12} cy={-12} r={4.5} fill={color} />
                          <text
                            x={24}
                            y={-7}
                            fill="#f8fafc"
                            fontSize={12.5}
                            fontWeight="600"
                            fontFamily="var(--font-family, sans-serif)"
                          >
                            #{idx + 1} {item.display_name.length > 20 ? `${item.display_name.slice(0, 18)}…` : item.display_name}
                          </text>

                          {/* Uncertainty Review Warning Badge */}
                          {isReview && (
                            <g transform={`translate(${labelWidth + 6}, 0)`}>
                              <rect
                                x={0}
                                y={-24}
                                width={124}
                                height={24}
                                rx={5}
                                fill="#f59e0b"
                              />
                              <text
                                x={8}
                                y={-7}
                                fill="#000000"
                                fontSize={11}
                                fontWeight="700"
                                fontFamily="var(--font-family, sans-serif)"
                              >
                                ⚠️ Review Height
                              </text>
                            </g>
                          )}
                        </g>

                        {/* Interactive Dimension Tooltip Badge on Hover */}
                        {isHovered && (
                          <g transform={`translate(${x1 + w / 2 - 90}, ${y2 + 28})`}>
                            <rect
                              x={0}
                              y={-22}
                              width={180}
                              height={26}
                              rx={6}
                              fill="#0f172a"
                              stroke="#38bdf8"
                              strokeWidth={1.5}
                              opacity={0.96}
                            />
                            <text
                              x={90}
                              y={-5}
                              textAnchor="middle"
                              fill="#38bdf8"
                              fontSize={12}
                              fontWeight="600"
                              fontFamily="var(--font-mono, monospace)"
                            >
                              {lengthMm} × {widthMm} × {heightMm} mm
                            </text>
                          </g>
                        )}
                      </g>
                    );
                  })}
                </svg>
              )}
            </div>
          ) : (
            <div className="stage-empty">
              <span>No image captured. Upload photos below or click a Demo Preset.</span>
            </div>
          )}
        </div>
      </div>

      {/* Upload Dropzones */}
      <div className="upload-dropzones">
        <div className="dropzone">
          <label className="dropzone-label">
            <strong>Top-Down View (Zenith) *</strong>
            <input type="file" accept="image/*" onChange={handleTopFileChange} />
            <div className="preview-container">
              <span className="file-name">
                {topFile ? topFile.name : "📷 Trial02_topdown.JPG (Loaded)"}
              </span>
            </div>
          </label>
        </div>

        <div className="dropzone">
          <label className="dropzone-label">
            <strong>Oblique View (35°–45°)</strong>
            <input type="file" accept="image/*" onChange={handleObliqueFileChange} />
            <div className="preview-container">
              <span className="file-name">
                {obliqueFile ? obliqueFile.name : "📷 Trial02_Oblique.JPG (Loaded)"}
              </span>
            </div>
          </label>
        </div>
      </div>

      {/* Main Analyze Button */}
      <div className="btn-group">
        <button
          className="btn btn-primary btn-full-width"
          onClick={handleUploadAndAnalyze}
          disabled={loading}
        >
          {loading ? "Analyzing Scene (CV + Meta Model API)..." : "⚡ Analyze Live Order"}
        </button>
      </div>

      {/* Demo Presets Selector */}
      <div className="demo-preset-section">
        <div className="demo-preset-label">
          <span>🚀 Instant Demo Presets (Zero-Camera / Pitch Mode):</span>
        </div>
        <div className="demo-preset-buttons">
          <button
            type="button"
            className={`btn-preset ${selectedPreset === 1 ? "active" : ""}`}
            onClick={() => handleLoadPreset(1)}
            disabled={loading}
          >
            <strong>Preset 1: Standard</strong>
            <span>4 Items (Optimal BOX-M)</span>
          </button>

          <button
            type="button"
            className={`btn-preset ${selectedPreset === 2 ? "active" : ""}`}
            onClick={() => handleLoadPreset(2)}
            disabled={loading}
          >
            <strong>Preset 2: Review Alert</strong>
            <span>Fragile & ±25mm Height Review</span>
          </button>

          <button
            type="button"
            className={`btn-preset ${selectedPreset === 3 ? "active" : ""}`}
            onClick={() => handleLoadPreset(3)}
            disabled={loading}
          >
            <strong>Preset 3: Multi-Carton</strong>
            <span>8 Items (Split Box 1 + Box 2)</span>
          </button>
        </div>
      </div>
    </div>
  );
};
