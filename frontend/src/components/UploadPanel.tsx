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

const SAMPLE_TOP = "/samples/topdown_sample.jpg";
const SAMPLE_OBLIQUE = "/samples/oblique_sample.jpg";

const PRESETS = [
  { id: 1, label: "Standard" },
  { id: 2, label: "Review" },
  { id: 3, label: "Multi-box" },
];

export const UploadPanel: React.FC<UploadPanelProps> = ({
  onAnalysisLoaded,
  loading,
  setLoading,
  analysis,
  items = [],
}) => {
  const [topFile, setTopFile] = useState<File | null>(null);
  const [obliqueFile, setObliqueFile] = useState<File | null>(null);
  const [topPreview, setTopPreview] = useState<string>(SAMPLE_TOP);
  const [selectedPreset, setSelectedPreset] = useState<number>(1);
  const [hoveredItemId, setHoveredItemId] = useState<string | null>(null);

  // Revoke blob URLs to prevent browser memory leaks
  useEffect(() => {
    return () => {
      if (topPreview.startsWith("blob:")) URL.revokeObjectURL(topPreview);
    };
  }, [topPreview]);

  const handleTopFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setTopFile(file);
    setTopPreview(file ? URL.createObjectURL(file) : SAMPLE_TOP);
  };

  const handleObliqueFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setObliqueFile(e.target.files?.[0] || null);
  };

  const handleLoadPreset = (presetNumber: number) => {
    setSelectedPreset(presetNumber);
    setLoading(true);

    setTimeout(() => {
      if (presetNumber === 1) {
        onAnalysisLoaded(orderAnalysisSample as unknown as OrderAnalysisResponse);
      } else if (presetNumber === 2) {
        onAnalysisLoaded(
          preset2UncertainReview as unknown as OrderAnalysisResponse,
          preset2PackingSolution as unknown as PackingSolutionResponse
        );
      } else {
        onAnalysisLoaded(
          preset3OrderAnalysis as unknown as OrderAnalysisResponse,
          preset3MultiCartonSplit as unknown as PackingSolutionResponse
        );
      }
      setLoading(false);
    }, 350);
  };

  const handleAnalyze = async () => {
    if (!topFile) {
      alert("Please select a top-down image or choose a preset.");
      return;
    }
    setLoading(true);
    const formData = new FormData();
    formData.append("top_image", topFile);
    if (obliqueFile) formData.append("oblique_image", obliqueFile);
    formData.append("capture_mode", obliqueFile ? "dual_photo" : "single_top_photo");

    try {
      const data = await OptiPackClient.analyzeOrder(formData);
      onAnalysisLoaded(data);
    } catch (err) {
      console.error("[UploadPanel] Analysis request failed:", err);
      alert(`Analysis failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  };

  // SVG coordinate space: bundled sample is 1280x960; expand if bboxes exceed it
  const analysisItems = analysis?.items || [];
  const vbW = Math.max(1280, ...analysisItems.map((it) => it.visual_evidence?.bbox_2d_px?.[2] || 0));
  const vbH = Math.max(960, ...analysisItems.map((it) => it.visual_evidence?.bbox_2d_px?.[3] || 0));

  return (
    <section className="panel">
      <header className="panel-head">
        <h2>Capture</h2>
        <div className="segmented">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              className={selectedPreset === p.id ? "is-active" : ""}
              onClick={() => handleLoadPreset(p.id)}
              disabled={loading}
            >
              {p.label}
            </button>
          ))}
        </div>
      </header>

      <div className="stage">
        <img src={topPreview} alt="Top-down capture" className="stage-img" />

        {loading && (
          <div className="stage-scan">
            <div className="stage-scan-line" />
            <span className="stage-scan-label">Analyzing…</span>
          </div>
        )}

        {!loading && analysisItems.length > 0 && (
          <svg className="stage-svg" viewBox={`0 0 ${vbW} ${vbH}`} preserveAspectRatio="xMidYMid meet">
            {analysisItems.map((item, idx) => {
              const [x1, y1, x2, y2] = item.visual_evidence?.bbox_2d_px || [0, 0, 0, 0];
              const w = Math.max(10, x2 - x1);
              const h = Math.max(10, y2 - y1);
              const color = item.visual_evidence?.display_color_hex || "#0071e3";
              const hovered = hoveredItemId === item.item_id;
              const review =
                item.measurement_provenance?.requires_user_review ||
                (item.uncertainty_mm?.height_sigma_mm || 0) > 8;
              const m = items.find((mi) => mi.item_id === item.item_id)?.dimensions_mm || item.dimensions_mm;
              const label = hovered
                ? `${item.display_name} · ${m.length_mm}×${m.width_mm}×${m.height_mm} mm`
                : `${idx + 1}`;
              const labelW = hovered ? Math.max(160, label.length * 15) : 44;

              return (
                <g
                  key={item.item_id}
                  className="bbox"
                  onMouseEnter={() => setHoveredItemId(item.item_id)}
                  onMouseLeave={() => setHoveredItemId(null)}
                >
                  <rect
                    x={x1}
                    y={y1}
                    width={w}
                    height={h}
                    rx={8}
                    fill={color}
                    fillOpacity={hovered ? 0.18 : 0.06}
                    stroke={review ? "#ff9f0a" : color}
                    strokeWidth={hovered ? 4 : 3}
                    strokeDasharray={review ? "14 8" : undefined}
                  />
                  <g transform={`translate(${x1 + 10}, ${y1 + 10})`}>
                    <rect width={labelW} height={40} rx={20} fill="rgba(255,255,255,0.94)" />
                    <text
                      x={labelW / 2}
                      y={27}
                      textAnchor="middle"
                      fontSize={24}
                      fontWeight={600}
                      fill="#1d1d1f"
                    >
                      {label}
                    </text>
                  </g>
                </g>
              );
            })}
          </svg>
        )}
      </div>

      <div className="capture-row">
        <label className="file-chip" title="Top-down photo">
          <input type="file" accept="image/*" onChange={handleTopFileChange} />
          <span className="file-chip-key">Top</span>
          <span className="file-chip-val">{topFile ? topFile.name : "Choose…"}</span>
        </label>
        <label className="file-chip" title="Oblique photo (optional)">
          <input type="file" accept="image/*" onChange={handleObliqueFileChange} />
          <span className="file-chip-key">Oblique</span>
          <span className="file-chip-val">{obliqueFile ? obliqueFile.name : "Optional"}</span>
        </label>
        <button type="button" className="btn btn-primary" onClick={handleAnalyze} disabled={loading}>
          {loading ? "Analyzing…" : "Analyze"}
        </button>
      </div>
    </section>
  );
};
