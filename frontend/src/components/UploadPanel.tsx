import React, { useEffect, useState } from "react";
import { OrderAnalysisResponse, PackingSolutionResponse } from "../types/contract";
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
}

export const UploadPanel: React.FC<UploadPanelProps> = ({
  onAnalysisLoaded,
  loading,
  setLoading,
}) => {
  const [topFile, setTopFile] = useState<File | null>(null);
  const [obliqueFile, setObliqueFile] = useState<File | null>(null);
  const [topPreview, setTopPreview] = useState<string | null>(null);
  const [obliquePreview, setObliquePreview] = useState<string | null>(null);
  const [selectedPreset, setSelectedPreset] = useState<number>(1);

  // Clean up object URLs to prevent browser memory leaks
  useEffect(() => {
    return () => {
      if (topPreview) URL.revokeObjectURL(topPreview);
      if (obliquePreview) URL.revokeObjectURL(obliquePreview);
    };
  }, [topPreview, obliquePreview]);

  const handleTopFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setTopFile(file);
    if (topPreview) URL.revokeObjectURL(topPreview);
    if (file) {
      setTopPreview(URL.createObjectURL(file));
    } else {
      setTopPreview(null);
    }
  };

  const handleObliqueFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setObliqueFile(file);
    if (obliquePreview) URL.revokeObjectURL(obliquePreview);
    if (file) {
      setObliquePreview(URL.createObjectURL(file));
    } else {
      setObliquePreview(null);
    }
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
    if (!topFile) {
      alert("Please select at least a top-down image or choose one of the 3 Demo Presets below.");
      return;
    }

    setLoading(true);
    const formData = new FormData();
    formData.append("top_image", topFile);
    if (obliqueFile) {
      formData.append("oblique_image", obliqueFile);
    }
    formData.append("capture_mode", obliqueFile ? "dual_photo" : "single_top_photo");

    try {
      const data = await OptiPackClient.analyzeOrder(formData);
      onAnalysisLoaded(data);
    } catch (err) {
      console.error("[UploadPanel] Analysis request failed:", err);
      alert(`Phân tích đơn hàng thất bại: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  };

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

      {/* Upload Dropzones */}
      <div className="upload-dropzones">
        <div className="dropzone">
          <label className="dropzone-label">
            <strong>Top-Down View (Zenith) *</strong>
            <input type="file" accept="image/*" onChange={handleTopFileChange} />
            {topPreview ? (
              <div className="preview-container">
                <img src={topPreview} alt="Top Preview" className="img-thumbnail" />
                <span className="file-name">{topFile?.name}</span>
              </div>
            ) : (
              <span className="file-name">Choose top-down image...</span>
            )}
          </label>
        </div>

        <div className="dropzone">
          <label className="dropzone-label">
            <strong>Oblique View (35°–45°)</strong>
            <input type="file" accept="image/*" onChange={handleObliqueFileChange} />
            {obliquePreview ? (
              <div className="preview-container">
                <img src={obliquePreview} alt="Oblique Preview" className="img-thumbnail" />
                <span className="file-name">{obliqueFile?.name}</span>
              </div>
            ) : (
              <span className="file-name">Choose oblique image (optional)...</span>
            )}
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
            className={`btn-preset ${selectedPreset === 1 ? "active" : ""}`}
            onClick={() => handleLoadPreset(1)}
            disabled={loading}
          >
            <strong>Preset 1: Standard</strong>
            <span>4 Items (Optimal BOX-M)</span>
          </button>

          <button
            className={`btn-preset ${selectedPreset === 2 ? "active" : ""}`}
            onClick={() => handleLoadPreset(2)}
            disabled={loading}
          >
            <strong>Preset 2: Review Alert</strong>
            <span>Fragile & ±25mm Height Review</span>
          </button>

          <button
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
