import React from "react";
import { Dimensions3D } from "../types/contract";

interface CartonControlBarProps {
  cartonMode: "auto" | "preset" | "custom";
  setCartonMode: (mode: "auto" | "preset" | "custom") => void;
  selectedCartonSku: string;
  setSelectedCartonSku: (sku: string) => void;
  customCartonDims: Dimensions3D;
  setCustomCartonDims: (dims: Dimensions3D) => void;
  onApply: () => void;
  loading: boolean;
  currentCartonSku?: string;
  currentCartonDims?: Dimensions3D;
}

const PRESET_CARTONS = [
  { sku: "BOX-S", label: "BOX-S (Small Mailer)", dims: "200 × 150 × 100 mm" },
  { sku: "BOX-M", label: "BOX-M (Medium Standard)", dims: "300 × 220 × 150 mm" },
  { sku: "BOX-L", label: "BOX-L (Large Carton)", dims: "400 × 300 × 200 mm" },
  { sku: "BOX-XL", label: "BOX-XL (Extra-Large)", dims: "500 × 350 × 250 mm" },
  { sku: "BOX-XXL", label: "BOX-XXL (Heavy Bulk)", dims: "600 × 400 × 350 mm" },
];

export const CartonControlBar: React.FC<CartonControlBarProps> = ({
  cartonMode,
  setCartonMode,
  selectedCartonSku,
  setSelectedCartonSku,
  customCartonDims,
  setCustomCartonDims,
  onApply,
  loading,
  currentCartonSku,
  currentCartonDims,
}) => {
  return (
    <div className="card carton-control-card">
      <div className="carton-control-header">
        <div className="carton-control-title">
          <h3>📦 Carton Sizing & Specification</h3>
          {currentCartonDims && (
            <span className="carton-current-badge">
              Active: <strong>{currentCartonSku || "BOX"}</strong> ({currentCartonDims.length_mm} × {currentCartonDims.width_mm} × {currentCartonDims.height_mm} mm)
            </span>
          )}
        </div>

        {/* Mode Selector Segmented Pills */}
        <div className="btn-group-pill carton-mode-pills">
          <button
            className={`btn-pill ${cartonMode === "auto" ? "active" : ""}`}
            onClick={() => {
              setCartonMode("auto");
            }}
            title="Automatically recommend the smallest feasible standard carton"
          >
            ✨ Auto Optimal
          </button>
          <button
            className={`btn-pill ${cartonMode === "preset" ? "active" : ""}`}
            onClick={() => {
              setCartonMode("preset");
            }}
            title="Lock to a specific standard carton SKU"
          >
            📋 Standard SKU
          </button>
          <button
            className={`btn-pill ${cartonMode === "custom" ? "active" : ""}`}
            onClick={() => {
              setCartonMode("custom");
            }}
            title="Specify custom carton dimensions in mm"
          >
            ✏️ Custom Size
          </button>
        </div>
      </div>

      <div className="carton-control-body">
        {cartonMode === "auto" && (
          <div className="carton-mode-desc">
            <span>
              The CP-SAT solver tests all 5 standard catalog cartons and automatically selects the smallest box that packs 100% of items with valid 3D support and zero overlap.
            </span>
          </div>
        )}

        {cartonMode === "preset" && (
          <div className="carton-preset-row">
            <label className="carton-input-label">Select Standard Box SKU:</label>
            <select
              className="carton-select"
              value={selectedCartonSku}
              onChange={(e) => {
                setSelectedCartonSku(e.target.value);
              }}
            >
              {PRESET_CARTONS.map((p) => (
                <option key={p.sku} value={p.sku}>
                  {p.label} — {p.dims}
                </option>
              ))}
            </select>
            <button
              className="btn btn-sm btn-accent"
              onClick={onApply}
              disabled={loading}
            >
              {loading ? "Packing..." : "Apply Box"}
            </button>
          </div>
        )}

        {cartonMode === "custom" && (
          <div className="carton-custom-row">
            <div className="custom-dim-group">
              <label>Length (mm):</label>
              <input
                type="number"
                min="50"
                max="2000"
                value={customCartonDims.length_mm}
                onChange={(e) =>
                  setCustomCartonDims({
                    ...customCartonDims,
                    length_mm: Math.max(50, parseInt(e.target.value) || 50),
                  })
                }
              />
            </div>
            <span className="dim-times">×</span>
            <div className="custom-dim-group">
              <label>Width (mm):</label>
              <input
                type="number"
                min="50"
                max="2000"
                value={customCartonDims.width_mm}
                onChange={(e) =>
                  setCustomCartonDims({
                    ...customCartonDims,
                    width_mm: Math.max(50, parseInt(e.target.value) || 50),
                  })
                }
              />
            </div>
            <span className="dim-times">×</span>
            <div className="custom-dim-group">
              <label>Height (mm):</label>
              <input
                type="number"
                min="30"
                max="2000"
                value={customCartonDims.height_mm}
                onChange={(e) =>
                  setCustomCartonDims({
                    ...customCartonDims,
                    height_mm: Math.max(30, parseInt(e.target.value) || 30),
                  })
                }
              />
            </div>
            <button
              className="btn btn-sm btn-accent"
              onClick={onApply}
              disabled={loading}
            >
              {loading ? "Packing..." : "Apply Custom Size"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
