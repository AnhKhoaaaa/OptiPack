import React, { useEffect, useRef, useState } from "react";
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
  onReset?: () => void;
}

const SAMPLE_TOP = "/samples/topdown_sample.jpg";
const SAMPLE_OBLIQUE = "/samples/oblique_sample.jpg";

const PRESETS = [
  { id: 1, label: "Preset: Standard" },
  { id: 2, label: "Preset: Review" },
  { id: 3, label: "Preset: Multi-box" },
];

export const UploadPanel: React.FC<UploadPanelProps> = ({
  onAnalysisLoaded,
  loading,
  setLoading,
  analysis,
  items = [],
  onReset,
}) => {
  const [mode, setMode] = useState<"idle" | "camera" | "upload">("idle");
  const [cameraStep, setCameraStep] = useState<"top" | "oblique">("top");
  const [cameraError, setCameraError] = useState<string | null>(null);

  const [topFile, setTopFile] = useState<File | Blob | null>(null);
  const [obliqueFile, setObliqueFile] = useState<File | Blob | null>(null);
  const [topPreview, setTopPreview] = useState<string | null>(null);
  const [obliquePreview, setObliquePreview] = useState<string | null>(null);

  const [hoveredItemId, setHoveredItemId] = useState<string | null>(null);
  const [selectedPreset, setSelectedPreset] = useState<number | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Stop camera stream helper
  const stopCameraStream = () => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
  };

  // Clean up object URLs and camera on unmount
  useEffect(() => {
    return () => {
      stopCameraStream();
      if (topPreview && topPreview.startsWith("blob:")) URL.revokeObjectURL(topPreview);
      if (obliquePreview && obliquePreview.startsWith("blob:")) URL.revokeObjectURL(obliquePreview);
    };
  }, []);

  // Start live webcam
  const startCamera = async () => {
    setCameraError(null);
    setCameraStep("top");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "environment",
          width: { ideal: 1280 },
          height: { ideal: 960 },
        },
        audio: false,
      });
      mediaStreamRef.current = stream;
      setMode("camera");
      // Give React a tick to mount video element
      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch((err) => console.warn("Video play interrupted:", err));
        }
      }, 50);
    } catch (err) {
      console.error("Camera access failed:", err);
      setCameraError("Camera unavailable or permission denied. Please upload photos instead.");
      setMode("upload");
    }
  };

  const cancelCamera = () => {
    stopCameraStream();
    setMode("idle");
    setCameraStep("top");
  };

  // Snap photo from video feed
  const captureFrame = (step: "top" | "oblique") => {
    const video = videoRef.current;
    if (!video) return;

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 960;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        const previewUrl = URL.createObjectURL(blob);

        if (step === "top") {
          setTopFile(blob);
          setTopPreview(previewUrl);
          setCameraStep("oblique"); // Next step: Oblique angle
        } else {
          setObliqueFile(blob);
          setObliquePreview(previewUrl);
          stopCameraStream();
          setMode("idle");

          // Automatically trigger analysis with both captured photos!
          if (topFile) {
            triggerAnalysis(topFile, blob);
          }
        }
      },
      "image/jpeg",
      0.92
    );
  };

  // Trigger Backend Analysis
  const triggerAnalysis = async (top: File | Blob, oblique?: File | Blob | null) => {
    setLoading(true);
    const formData = new FormData();
    formData.append("top_image", top, "zenith_top.jpg");
    if (oblique) {
      formData.append("oblique_image", oblique, "oblique.jpg");
    }
    formData.append("capture_mode", oblique ? "dual_photo" : "zenith_only");

    try {
      const data = await OptiPackClient.analyzeOrder(formData);
      onAnalysisLoaded(data);
    } catch (err) {
      console.error("[UploadPanel] Analysis failed:", err);
      alert(`Order analysis failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  };

  // Upload handlers
  const handleMultipleFilesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const file1 = files[0];
    const file2 = files.length > 1 ? files[1] : null;

    setTopFile(file1);
    setTopPreview(URL.createObjectURL(file1));

    if (file2) {
      setObliqueFile(file2);
      setObliquePreview(URL.createObjectURL(file2));
      // Two files provided: automatically analyze!
      triggerAnalysis(file1, file2);
    } else {
      // One file provided: user can choose oblique or analyze zenith-only
      triggerAnalysis(file1, null);
    }
  };

  // Preset loader for instant demo pitch
  const handleLoadPreset = (presetNumber: number) => {
    setSelectedPreset(presetNumber);
    stopCameraStream();
    setMode("idle");
    setTopFile(null);
    setObliqueFile(null);
    setTopPreview(SAMPLE_TOP);
    setObliquePreview(SAMPLE_OBLIQUE);
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
    }, 300);
  };

  const handleResetOrder = () => {
    stopCameraStream();
    setMode("idle");
    setTopFile(null);
    setObliqueFile(null);
    setTopPreview(null);
    setObliquePreview(null);
    setSelectedPreset(null);
    if (onReset) onReset();
  };

  const analysisItems = analysis?.items || [];
  const vbW = Math.max(1280, ...analysisItems.map((it) => it.visual_evidence?.bbox_2d_px?.[2] || 0));
  const vbH = Math.max(960, ...analysisItems.map((it) => it.visual_evidence?.bbox_2d_px?.[3] || 0));

  const hasCapturedContent = !!topPreview || !!analysis;

  return (
    <section className="panel">
      {/* Header with clean actions */}
      <header className="panel-head">
        <h2>Capture</h2>
        <div className="head-actions">
          {hasCapturedContent && (
            <button type="button" className="btn-link text-sm" onClick={handleResetOrder}>
              New capture
            </button>
          )}
          <div className="segmented">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                className={selectedPreset === p.id ? "is-active" : ""}
                onClick={() => handleLoadPreset(p.id)}
                disabled={loading}
              >
                {p.label.replace("Preset: ", "")}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* Main Viewport / Stage */}
      <div className="stage">
        {/* Mode 1: Live Webcam Viewfinder */}
        {mode === "camera" && (
          <div className="camera-viewfinder">
            <video ref={videoRef} autoPlay playsInline muted className="camera-video" />
            <div className="camera-hud">
              <div className="camera-step-pill">
                <span className="camera-dot" />
                <span>
                  {cameraStep === "top"
                    ? "Step 1 of 2: Overhead (Top-Down Zenith View)"
                    : "Step 2 of 2: Tilt 35°–45° (Oblique Side View)"}
                </span>
              </div>

              <div className="camera-controls">
                <button type="button" className="btn-camera-cancel" onClick={cancelCamera}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="shutter-button"
                  onClick={() => captureFrame(cameraStep)}
                  title={cameraStep === "top" ? "Snap Top-Down Photo" : "Snap Oblique Photo & Analyze"}
                >
                  <span className="shutter-inner" />
                </button>
                <div style={{ width: 60 }} /> {/* Spacer for symmetry */}
              </div>
            </div>
          </div>
        )}

        {/* Mode 2: Loading / Laser Scanning HUD */}
        {loading && (
          <div className="stage-scan">
            <div className="stage-scan-line" />
            <span className="stage-scan-label">Processing dual photos with Meta AI…</span>
          </div>
        )}

        {/* Mode 3: Captured Photo with AI Bounding Boxes */}
        {mode !== "camera" && topPreview && (
          <>
            <img src={topPreview} alt="Top-down capture" className="stage-img" />

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
          </>
        )}

        {/* Mode 4: Empty Initial State ("Trống trống xíu" - Clean Minimal Entry) */}
        {mode !== "camera" && !topPreview && (
          <div className="stage-empty-clean">
            <div className="empty-prompt">
              <span className="empty-icon">📷</span>
              <h3>Capture Order on Calibration Board</h3>
              <p className="muted text-sm">
                Take or upload 2 photos (Top-down & Oblique) to measure items and pack.
              </p>
              <div className="empty-actions">
                <button type="button" className="btn btn-primary" onClick={startCamera}>
                  Open Camera
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => fileInputRef.current?.click()}
                >
                  Upload 2 Photos
                </button>
              </div>
              {cameraError && <p className="camera-err-hint">{cameraError}</p>}
            </div>
          </div>
        )}
      </div>

      {/* Hidden file input supporting multi-photo selection */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        style={{ display: "none" }}
        onChange={handleMultipleFilesChange}
      />

      {/* Bottom Bar when an image is active */}
      {mode !== "camera" && hasCapturedContent && (
        <div className="capture-row">
          <button type="button" className="btn btn-secondary btn-sm" onClick={startCamera}>
            📷 Retake with Camera
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => fileInputRef.current?.click()}
          >
            + Upload Photos
          </button>
          {obliquePreview && (
            <span className="muted text-xs" style={{ marginLeft: "auto" }}>
              ✓ Dual views loaded (Top + Oblique)
            </span>
          )}
        </div>
      )}
    </section>
  );
};
