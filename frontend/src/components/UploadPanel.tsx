import React, { useEffect, useRef, useState } from "react";
import { AITelemetry, OrderAnalysisResponse, PackingSolutionResponse } from "../types/contract";
import { ExtendedPackableItem } from "./ManifestTable";
import { OptiPackClient } from "../api/optipackClient";

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
  aiTelemetry?: AITelemetry;
}

const SAMPLE_TOP = "/samples/topdown_sample.jpg";
const SAMPLE_OBLIQUE = "/samples/oblique_sample.jpg";


// Helper to auto-orient portrait photos (H > W) into landscape (W > H)
// matching the A4 calibration sheet coordinate system
const normalizeToLandscape = (fileOrBlob: File | Blob): Promise<{ blob: Blob; url: string }> => {
  return new Promise((resolve) => {
    const tempUrl = URL.createObjectURL(fileOrBlob);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(tempUrl);
      if (img.naturalHeight > img.naturalWidth) {
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalHeight;
        canvas.height = img.naturalWidth;
        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.translate(canvas.width, 0);
          ctx.rotate((90 * Math.PI) / 180);
          ctx.drawImage(img, 0, 0);
          canvas.toBlob(
            (rotatedBlob) => {
              if (rotatedBlob) {
                resolve({ blob: rotatedBlob, url: URL.createObjectURL(rotatedBlob) });
                return;
              }
              resolve({ blob: fileOrBlob, url: URL.createObjectURL(fileOrBlob) });
            },
            "image/jpeg",
            0.95
          );
          return;
        }
      }
      resolve({ blob: fileOrBlob, url: URL.createObjectURL(fileOrBlob) });
    };
    img.onerror = () => {
      URL.revokeObjectURL(tempUrl);
      resolve({ blob: fileOrBlob, url: URL.createObjectURL(fileOrBlob) });
    };
    img.src = tempUrl;
  });
};

export const UploadPanel: React.FC<UploadPanelProps> = ({
  onAnalysisLoaded,
  loading,
  setLoading,
  analysis,
  items = [],
  onReset,
  aiTelemetry,
}) => {
  const [mode, setMode] = useState<"idle" | "camera" | "upload">("idle");
  const [cameraStep, setCameraStep] = useState<"top" | "oblique">("top");
  const [cameraError, setCameraError] = useState<string | null>(null);

  const [topFile, setTopFile] = useState<File | Blob | null>(null);
  const [obliqueFile, setObliqueFile] = useState<File | Blob | null>(null);
  const [topPreview, setTopPreview] = useState<string | null>(null);
  const [obliquePreview, setObliquePreview] = useState<string | null>(null);
  const [imgNaturalSize, setImgNaturalSize] = useState<{ w: number; h: number } | null>(null);

  const [hoveredItemId, setHoveredItemId] = useState<string | null>(null);

  const stageRef = useRef<HTMLDivElement | null>(null);
  const [stageWidth, setStageWidth] = useState<number>(0);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const topFileRef = useRef<File | Blob | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const topSingleInputRef = useRef<HTMLInputElement | null>(null);
  const obliqueSingleInputRef = useRef<HTMLInputElement | null>(null);
  const cameraTopInputRef = useRef<HTMLInputElement | null>(null);
  const cameraObliqueInputRef = useRef<HTMLInputElement | null>(null);

  // Measure stage width to scale SVG typography and badges dynamically
  useEffect(() => {
    if (!stageRef.current) return;
    const updateWidth = () => {
      if (stageRef.current) {
        const w = stageRef.current.clientWidth;
        if (w > 0) setStageWidth(w);
      }
    };
    updateWidth();
    const ro = new ResizeObserver(updateWidth);
    ro.observe(stageRef.current);
    window.addEventListener("resize", updateWidth);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", updateWidth);
    };
  }, [topPreview, mode]);

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

  // Start live webcam or native mobile camera
  const startCamera = async () => {
    setCameraError(null);
    setCameraStep("top");

    // Check if browser supports WebRTC live streaming (desktop or secure HTTPS context)
    const hasStreamSupport =
      typeof navigator !== "undefined" &&
      !!navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === "function";

    if (!hasStreamSupport) {
      // Mobile Safari / iOS over HTTP: trigger native high-res camera directly
      cameraTopInputRef.current?.click();
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "environment",
          width: { ideal: 1920, min: 1280 },
          height: { ideal: 1440, min: 720 },
        },
        audio: false,
      });
      mediaStreamRef.current = stream;
      setMode("camera");
      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch((err) => console.warn("Video play interrupted:", err));
        }
      }, 50);
    } catch (err) {
      console.warn("Webcam live stream unavailable, falling back to native camera:", err);
      // Fallback to native mobile camera
      cameraTopInputRef.current?.click();
    }
  };

  const handleNativeCameraTop = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const topRes = await normalizeToLandscape(file);
    topFileRef.current = topRes.blob;
    setTopFile(topRes.blob);
    setTopPreview(topRes.url);
    setCameraStep("oblique");
    e.target.value = "";

    // Automatically prompt photo 2 after a brief delay
    setTimeout(() => {
      cameraObliqueInputRef.current?.click();
    }, 450);
  };

  const handleNativeCameraOblique = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const oblRes = await normalizeToLandscape(file);
    setObliqueFile(oblRes.blob);
    setObliquePreview(oblRes.url);
    e.target.value = "";

    const topBlob = topFileRef.current || topFile;
    if (topBlob) {
      triggerAnalysis(topBlob, oblRes.blob);
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

    const rawW = video.videoWidth || 1920;
    const rawH = video.videoHeight || 1080;
    const isPortrait = rawH > rawW;

    const canvas = document.createElement("canvas");
    canvas.width = isPortrait ? rawH : rawW;
    canvas.height = isPortrait ? rawW : rawH;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    if (isPortrait) {
      ctx.translate(canvas.width, 0);
      ctx.rotate((90 * Math.PI) / 180);
      ctx.drawImage(video, 0, 0);
    } else {
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    }
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        const previewUrl = URL.createObjectURL(blob);

        if (step === "top") {
          topFileRef.current = blob;
          setTopFile(blob);
          setTopPreview(previewUrl);
          setCameraStep("oblique");
        } else {
          setObliqueFile(blob);
          setObliquePreview(previewUrl);
          stopCameraStream();
          setMode("idle");

          const topBlob = topFileRef.current || topFile;
          if (topBlob) {
            triggerAnalysis(topBlob, blob);
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
    setCameraError(null);
    onReset?.();
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
      setCameraError(`Order analysis failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  };

  // Multi-photo upload handler with auto-orientation normalization
  const handleMultipleFilesChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const file1 = files[0];
    const file2 = files.length > 1 ? files[1] : null;
    // Allow re-selecting the same photos after New capture or a failed analysis.
    e.target.value = "";

    const topRes = await normalizeToLandscape(file1);
    setTopFile(topRes.blob);
    setTopPreview(topRes.url);

    if (file2) {
      const oblRes = await normalizeToLandscape(file2);
      setObliqueFile(oblRes.blob);
      setObliquePreview(oblRes.url);
      triggerAnalysis(topRes.blob, oblRes.blob);
    } else if (obliqueFile) {
      triggerAnalysis(topRes.blob, obliqueFile);
    }
  };

  const handleSingleTopChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const topRes = await normalizeToLandscape(file);
    topFileRef.current = topRes.blob;
    setTopFile(topRes.blob);
    setTopPreview(topRes.url);
    e.target.value = "";
    if (obliqueFile) {
      triggerAnalysis(topRes.blob, obliqueFile);
    }
  };

  const handleSingleObliqueChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const oblRes = await normalizeToLandscape(file);
    setObliqueFile(oblRes.blob);
    setObliquePreview(oblRes.url);
    e.target.value = "";
    const topBlob = topFileRef.current || topFile;
    if (topBlob) {
      triggerAnalysis(topBlob, oblRes.blob);
    }
  };

  // Load real benchmark sample photos and trigger full end-to-end CV + AI analysis
  const handleLoadSamplePhotos = async () => {
    setCameraError(null);
    stopCameraStream();
    setMode("idle");
    setLoading(true);

    try {
      const [topRes, oblRes] = await Promise.all([
        fetch(SAMPLE_TOP),
        fetch(SAMPLE_OBLIQUE),
      ]);
      if (!topRes.ok || !oblRes.ok) {
        throw new Error("Unable to load benchmark sample photos from server.");
      }
      const [topBlob, oblBlob] = await Promise.all([
        topRes.blob(),
        oblRes.blob(),
      ]);

      const topFileObj = new File([topBlob], "zenith_top.jpg", { type: "image/jpeg" });
      const oblFileObj = new File([oblBlob], "oblique_photo.jpg", { type: "image/jpeg" });

      setTopFile(topFileObj);
      setObliqueFile(oblFileObj);
      setTopPreview(SAMPLE_TOP);
      setObliquePreview(SAMPLE_OBLIQUE);

      await triggerAnalysis(topFileObj, oblFileObj);
    } catch (err) {
      console.error("[UploadPanel] Loading sample photos failed:", err);
      setCameraError(err instanceof Error ? err.message : "Failed to load benchmark sample photos");
      setLoading(false);
    }
  };

  const handleResetOrder = () => {
    setCameraError(null);
    stopCameraStream();
    setMode("idle");
    setTopFile(null);
    setObliqueFile(null);
    setTopPreview(null);
    setObliquePreview(null);
    setImgNaturalSize(null);
    if (onReset) onReset();
  };

  const analysisItems = analysis?.items || [];
  const rawMaxX = Math.max(0, ...analysisItems.map((it) => it.visual_evidence?.bbox_2d_px?.[2] || 0));
  const rawMaxY = Math.max(0, ...analysisItems.map((it) => it.visual_evidence?.bbox_2d_px?.[3] || 0));

  // Auto-detect if bounding boxes were authored for 1280x960 mock coordinate space
  // while displayed photo is high-resolution (e.g. 4032x3024)
  const isSampleMock = analysis?.analysis_id?.startsWith("ord_20261027_") ?? false;
  const isLegacy1280 =
    (isSampleMock || (rawMaxX > 0 && rawMaxX <= 1350 && rawMaxY <= 1000)) &&
    !!imgNaturalSize &&
    imgNaturalSize.w > 1600;

  const coordScaleX = isLegacy1280 && imgNaturalSize ? imgNaturalSize.w / 1280 : 1;
  const coordScaleY = isLegacy1280 && imgNaturalSize ? imgNaturalSize.h / 960 : 1;

  const maxScaledX = rawMaxX * coordScaleX;
  const maxScaledY = rawMaxY * coordScaleY;
  const vbW = imgNaturalSize ? imgNaturalSize.w : Math.max(1280, maxScaledX);
  const vbH = imgNaturalSize ? imgNaturalSize.h : Math.max(960, maxScaledY);

  // SVG-to-display pixel ratio: ensures strokes, fonts and badges are consistent on all screen sizes
  const displayW =
    stageWidth > 0
      ? stageWidth
      : typeof window !== "undefined" && window.innerWidth < 640
      ? 360
      : 720;
  const pxToSvg = vbW / displayW;

  const hasCapturedContent = !!topPreview || !!analysis;
  const telemetry = aiTelemetry || analysis?.ai_telemetry;

  return (
    <section className="panel">
      {/* Header with clean actions */}
      <header className="panel-head">
        <div className="head-actions">
          <h2>Capture</h2>
          {telemetry && (
            <span
              className={`telemetry-pill ${
                telemetry.muse_status === "success" || telemetry.muse_status === "cached"
                  ? "is-ok"
                  : "is-fallback"
              }`}
              title={`Model: ${telemetry.muse_model} · Status: ${telemetry.muse_status}`}
            >
              {telemetry.muse_status === "success"
                ? "Online · Muse 1.3"
                : telemetry.muse_status === "cached"
                ? "Cached · Muse 1.3"
                : "Offline Local Mode"}
            </span>
          )}
        </div>
        <div className="head-actions">
          {hasCapturedContent && (
            <button type="button" className="btn-link text-sm" onClick={handleResetOrder}>
              New capture
            </button>
          )}
        </div>
      </header>

      {/* Main Viewport / Stage */}
      <div className={`stage ${!analysis && mode !== "camera" ? "is-initial" : ""}`} ref={stageRef}>
        {/* Mode 1: Live Webcam Viewfinder */}
        {mode === "camera" && (
          <div className="camera-viewfinder">
            <video ref={videoRef} autoPlay playsInline muted className="camera-video" />
            <div className="camera-hud">
              <div className={`camera-step-pill ${cameraStep === "oblique" ? "is-step2" : ""}`}>
                <span className="camera-dot" />
                <span>
                  {cameraStep === "top"
                    ? "Step 1/2: Position camera directly above (Zenith view)"
                    : "Step 2/2: Tilt camera 35°–45° (Oblique view) and capture"}
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
                <div style={{ width: 60 }} />
              </div>
            </div>
          </div>
        )}

        {/* Mode 2: Loading / Laser Scanning HUD */}
        {loading && (
          <div className="stage-scan">
            <div className="stage-scan-line" />
            <span className="stage-scan-label">Analyzing items with Meta AI & computing 3D metrology (approx. 8–12s on first run)…</span>
          </div>
        )}

        {/* Mode 3: Captured Photo with AI Bounding Boxes (When Analysis is Loaded) */}
        {mode !== "camera" && analysis && topPreview && (
          <>
            <img
              src={topPreview}
              alt="Top-down capture"
              className="stage-img"
              onLoad={(e) => {
                const el = e.currentTarget;
                if (el.naturalWidth && el.naturalHeight) {
                  setImgNaturalSize({ w: el.naturalWidth, h: el.naturalHeight });
                }
              }}
            />

            {!loading && analysisItems.length > 0 && (
              <svg
                className="stage-svg"
                viewBox={`0 0 ${vbW} ${vbH}`}
                preserveAspectRatio="xMidYMid meet"
                onClick={() => setHoveredItemId(null)}
              >
                {analysisItems.map((item, idx) => {
                  const [rawX1, rawY1, rawX2, rawY2] = item.visual_evidence?.bbox_2d_px || [0, 0, 0, 0];
                  const x1 = rawX1 * coordScaleX;
                  const y1 = rawY1 * coordScaleY;
                  const x2 = rawX2 * coordScaleX;
                  const y2 = rawY2 * coordScaleY;
                  const w = Math.max(15 * pxToSvg, x2 - x1);
                  const h = Math.max(15 * pxToSvg, y2 - y1);
                  const color = item.visual_evidence?.display_color_hex || "#0071e3";
                  const hovered = hoveredItemId === item.item_id;
                  const review =
                    item.measurement_provenance?.requires_user_review ||
                    (item.uncertainty_mm?.height_sigma_mm || 0) > 8;
                  const matchedItem = items.find((mi) => mi.item_id === item.item_id);
                  const m = matchedItem?.dimensions_mm || item.dimensions_mm;
                  const dispName = matchedItem?.display_name || item.display_name;
                  const label = hovered
                    ? `${dispName} · ${m.length_mm}×${m.width_mm}×${m.height_mm} mm`
                    : `${idx + 1}`;

                  // Compute responsive badge geometry in SVG user units with edge boundary safety
                  const badgeHeightPx = 28;
                  const badgeHeight = Math.round(badgeHeightPx * pxToSvg);
                  const badgeRadius = Math.round((badgeHeightPx / 2) * pxToSvg);
                  const fontSizePx = hovered ? (displayW < 400 ? 11 : 13) : 15;
                  const fontSize = Math.round(fontSizePx * pxToSvg);
                  const offset = Math.round(8 * pxToSvg);
                  const boxRadius = Math.round(8 * pxToSvg);

                  const badgeWidthPx = hovered ? Math.max(140, label.length * (displayW < 400 ? 6.2 : 7.2) + 20) : 34;
                  const rawBadgeWidth = Math.round(badgeWidthPx * pxToSvg);
                  const badgeWidth = Math.min(vbW - 2 * offset, rawBadgeWidth);

                  // Keep badge inside stage viewport boundaries
                  const badgeX = Math.max(offset, Math.min(x1 + offset, vbW - badgeWidth - offset));
                  const badgeY = Math.max(offset, Math.min(y1 + offset, vbH - badgeHeight - offset));

                  return (
                    <g
                      key={item.item_id}
                      className="bbox"
                      onClick={(e) => {
                        e.stopPropagation();
                        setHoveredItemId(hovered ? null : item.item_id);
                      }}
                      onMouseEnter={() => setHoveredItemId(item.item_id)}
                      onMouseLeave={() => setHoveredItemId(null)}
                    >
                      <rect
                        x={x1}
                        y={y1}
                        width={w}
                        height={h}
                        rx={boxRadius}
                        fill={color}
                        fillOpacity={hovered ? 0.22 : 0.08}
                        stroke={review ? "#ff9f0a" : color}
                        strokeWidth={hovered ? 3.5 : 2.5}
                        vectorEffect="non-scaling-stroke"
                        strokeDasharray={review ? "10 6" : undefined}
                      />
                      <g transform={`translate(${badgeX}, ${badgeY})`} className="bbox-badge">
                        <rect
                          width={badgeWidth}
                          height={badgeHeight}
                          rx={badgeRadius}
                          fill="rgba(255, 255, 255, 0.95)"
                          stroke={hovered ? color : "rgba(0, 0, 0, 0.12)"}
                          strokeWidth={1.5}
                          vectorEffect="non-scaling-stroke"
                        />
                        <text
                          x={badgeWidth / 2}
                          y={badgeHeight / 2}
                          textAnchor="middle"
                          dominantBaseline="central"
                          fontSize={fontSize}
                          fontWeight={600}
                          fill="#1d1d1f"
                          style={{ pointerEvents: "none" }}
                        >
                          {label}
                        </text>
                      </g>
                    </g>
                  );
                })}
              </svg>
            )}

            {!loading && analysis && analysisItems.length === 0 && (
              <div className="calibration-banner-overlay">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="calib-warn-icon">
                  <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                  <line x1="12" y1="9" x2="12" y2="13"/>
                  <line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
                <strong>Calibration Board Not Detected</strong>
                <p className="muted text-xs" style={{ maxWidth: 300, textAlign: "center", lineHeight: 1.4 }}>
                  {analysis.global_warnings?.[0] ||
                    "OptiPack requires an A4 4-corner ArUco sheet to calculate exact physical millimeters from live photos."}
                </p>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  style={{ marginTop: 8 }}
                  onClick={handleLoadSamplePhotos}
                  disabled={loading}
                >
                  Try with benchmark sample photos
                </button>
              </div>
            )}
          </>
        )}

        {/* Mode 4: Initial eKYC-Style Dual-Card Capture */}
        {mode !== "camera" && !analysis && (
          <div className="dual-capture-wrapper">
            <div className="dual-capture-header">
              <h3>Capture Order</h3>
            </div>

            <div className="dual-capture-grid">
              {/* Box 1: Top-down View (Zenith) */}
              <div className="slot-col">
                <div
                  className={`capture-slot-card ${topPreview ? "has-image" : ""}`}
                  onClick={() => topSingleInputRef.current?.click()}
                  role="button"
                  tabIndex={0}
                  title="Top-down photo (90° overhead)"
                >
                  <div className="viewfinder-corner top-left" />
                  <div className="viewfinder-corner top-right" />
                  <div className="viewfinder-corner bottom-left" />
                  <div className="viewfinder-corner bottom-right" />

                  {topPreview ? (
                    <div className="slot-preview-wrapper">
                      <img src={topPreview} alt="Top view" className="slot-preview-img" />
                      <div className="slot-badge is-ready">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                        <span>Top View (90°)</span>
                      </div>
                      <button
                        type="button"
                        className="slot-action-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          topSingleInputRef.current?.click();
                        }}
                      >
                        Change
                      </button>
                    </div>
                  ) : (
                    <div className="slot-empty-content">
                      <div className="slot-icon-circle">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                          <circle cx="12" cy="13" r="4"/>
                        </svg>
                      </div>
                      <h4 className="slot-title">Top View</h4>
                      <div className="slot-cue-pill">90° Overhead</div>
                    </div>
                  )}
                </div>
              </div>

              {/* Box 2: Oblique View (Side tilt) */}
              <div className="slot-col">
                <div
                  className={`capture-slot-card ${obliquePreview ? "has-image" : ""}`}
                  onClick={() => obliqueSingleInputRef.current?.click()}
                  role="button"
                  tabIndex={0}
                  title="Side photo (45° angle)"
                >
                  <div className="viewfinder-corner top-left" />
                  <div className="viewfinder-corner top-right" />
                  <div className="viewfinder-corner bottom-left" />
                  <div className="viewfinder-corner bottom-right" />

                  {obliquePreview ? (
                    <div className="slot-preview-wrapper">
                      <img src={obliquePreview} alt="Side view" className="slot-preview-img" />
                      <div className="slot-badge is-ready">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                        <span>Side View (45°)</span>
                      </div>
                      <button
                        type="button"
                        className="slot-action-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          obliqueSingleInputRef.current?.click();
                        }}
                      >
                        Change
                      </button>
                    </div>
                  ) : (
                    <div className="slot-empty-content">
                      <div className="slot-icon-circle">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M2 22h20"/>
                          <path d="M2 22 17 7"/>
                          <path d="M9 22a7 7 0 0 0 7-7"/>
                        </svg>
                      </div>
                      <h4 className="slot-title">Side View</h4>
                      <div className="slot-cue-pill">45° Angle</div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Bottom Actions / CTA */}
            <div className="dual-capture-cta">
              {topFile && obliqueFile ? (
                <button
                  type="button"
                  className="btn btn-primary btn-lg pulse-cta"
                  onClick={() => triggerAnalysis(topFile, obliqueFile)}
                  disabled={loading}
                >
                  {loading ? (
                    "Analyzing…"
                  ) : (
                    <span className="btn-icon-label" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                      <span>Analyze Items</span>
                    </span>
                  )}
                </button>
              ) : topFile && !obliqueFile ? (
                <div className="cta-status-prompt">
                  <span className="cta-dot is-pending" />
                  <span>Tap right box for <strong>Side View</strong>.</span>
                </div>
              ) : !topFile && obliqueFile ? (
                <div className="cta-status-prompt">
                  <span className="cta-dot is-pending" />
                  <span>Tap left box for <strong>Top View</strong>.</span>
                </div>
              ) : (
                <div className="cta-empty-actions">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => fileInputRef.current?.click()}
                    style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    <span>Upload Photos</span>
                  </button>
                  <button
                    type="button"
                    className="btn-link text-xs"
                    onClick={handleLoadSamplePhotos}
                    disabled={loading}
                    title="Run with sample photos"
                  >
                    Try sample order
                  </button>
                </div>
              )}
            </div>
            {cameraError && <p className="camera-err-hint">{cameraError}</p>}
          </div>
        )}
      </div>

      {cameraError && <p className="camera-err-hint" role="alert">{cameraError}</p>}

      {/* Hidden file inputs */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        style={{ display: "none" }}
        onChange={handleMultipleFilesChange}
      />
      <input
        ref={topSingleInputRef}
        type="file"
        accept="image/*"
        style={{ display: "none" }}
        onChange={handleSingleTopChange}
      />
      <input
        ref={obliqueSingleInputRef}
        type="file"
        accept="image/*"
        style={{ display: "none" }}
        onChange={handleSingleObliqueChange}
      />
      {/* Mobile Native Camera Inputs (Zero-permission native camera trigger) */}
      <input
        ref={cameraTopInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        style={{ display: "none" }}
        onChange={handleNativeCameraTop}
      />
      <input
        ref={cameraObliqueInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        style={{ display: "none" }}
        onChange={handleNativeCameraOblique}
      />

      {/* Bottom Bar when an image is active */}
      {mode !== "camera" && analysis && hasCapturedContent && (
        <div className="capture-row">
          <button type="button" className="btn btn-secondary btn-sm" onClick={startCamera}>
            📷 Camera
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => topSingleInputRef.current?.click()}
            title="Select Top-Down (Zenith) Photo"
          >
            {topFile ? "✓ Top Photo" : "+ Top Photo"}
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => (topFile && !obliqueFile ? cameraObliqueInputRef.current?.click() : obliqueSingleInputRef.current?.click())}
            title="Select Oblique (35°-45°) Photo"
          >
            {obliqueFile || obliquePreview ? "✓ Oblique Photo" : "+ Oblique Photo"}
          </button>
          {topFile && !obliqueFile && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => cameraObliqueInputRef.current?.click()}
              style={{ marginLeft: "auto" }}
            >
              📷 Snap Oblique Photo
            </button>
          )}
          {topFile && obliqueFile && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => triggerAnalysis(topFile, obliqueFile)}
              disabled={loading}
              style={{ marginLeft: "auto" }}
            >
              {loading ? "Analyzing…" : "Analyze Live Order"}
            </button>
          )}
          {!topFile && obliquePreview && (
            <span className="muted text-xs" style={{ marginLeft: "auto" }}>
              ✓ Dual views loaded
            </span>
          )}
        </div>
      )}
    </section>
  );
};
