import React, { useState } from "react";
import { OrderAnalysisResponse } from "../types/contract";
import orderAnalysisSample from "../mocks/orderAnalysisSample.json";

interface UploadPanelProps {
  onAnalysisLoaded: (analysis: OrderAnalysisResponse) => void;
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

  const handleUseDemoPreset = () => {
    setLoading(true);
    setTimeout(() => {
      onAnalysisLoaded(orderAnalysisSample as unknown as OrderAnalysisResponse);
      setLoading(false);
    }, 400);
  };

  const handleUploadAndAnalyze = async () => {
    if (!topFile) {
      alert("Please select at least a top-down image or click 'Use Demo Preset'.");
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
      const res = await fetch("http://localhost:8000/api/v1/orders/analyze", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data: OrderAnalysisResponse = await res.json();
      onAnalysisLoaded(data);
    } catch (err) {
      console.warn("Backend not reached, falling back to local golden fixture.", err);
      onAnalysisLoaded(orderAnalysisSample as unknown as OrderAnalysisResponse);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card upload-card">
      <div className="card-header">
        <h2>1. Order Capture & Metrology</h2>
        <span className="badge badge-primary">Step 1 of 3</span>
      </div>

      <p className="card-desc">
        Capture or upload top-down + oblique images of items on the A4 ArUco calibration sheet, or use the pre-calibrated demo preset.
      </p>

      <div className="upload-dropzones">
        <div className="dropzone">
          <label className="dropzone-label">
            <strong>Top-Down View (Zenith) *</strong>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => setTopFile(e.target.files?.[0] || null)}
            />
            <span className="file-name">{topFile ? topFile.name : "Choose top-down image..."}</span>
          </label>
        </div>

        <div className="dropzone">
          <label className="dropzone-label">
            <strong>Oblique View (35°-45°)</strong>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => setObliqueFile(e.target.files?.[0] || null)}
            />
            <span className="file-name">{obliqueFile ? obliqueFile.name : "Choose oblique image (optional)..."}</span>
          </label>
        </div>
      </div>

      <div className="btn-group">
        <button
          className="btn btn-primary"
          onClick={handleUploadAndAnalyze}
          disabled={loading}
        >
          {loading ? "Analyzing Scene..." : "Analyze Order via CV & Meta API"}
        </button>
        <button
          className="btn btn-secondary"
          onClick={handleUseDemoPreset}
          disabled={loading}
        >
          Load Demo Preset (Instant)
        </button>
      </div>
    </div>
  );
};
