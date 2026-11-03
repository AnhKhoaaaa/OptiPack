import React, { useEffect, useState } from "react";
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
  // Local string buffers allow natural typing, deleting and editing without premature clamping
  const [lenStr, setLenStr] = useState<string>(String(customCartonDims.length_mm));
  const [widthStr, setWidthStr] = useState<string>(String(customCartonDims.width_mm));
  const [heightStr, setHeightStr] = useState<string>(String(customCartonDims.height_mm));

  // Sync buffers when incoming props change (e.g. preset selection)
  useEffect(() => {
    setLenStr(String(customCartonDims.length_mm));
    setWidthStr(String(customCartonDims.width_mm));
    setHeightStr(String(customCartonDims.height_mm));
  }, [customCartonDims.length_mm, customCartonDims.width_mm, customCartonDims.height_mm]);

  const commitCustomDims = () => {
    const l = Math.max(50, Math.min(2500, parseInt(lenStr, 10) || 50));
    const w = Math.max(50, Math.min(2500, parseInt(widthStr, 10) || 50));
    const h = Math.max(30, Math.min(2500, parseInt(heightStr, 10) || 30));

    setLenStr(String(l));
    setWidthStr(String(w));
    setHeightStr(String(h));

    setCustomCartonDims({ length_mm: l, width_mm: w, height_mm: h });
    return { length_mm: l, width_mm: w, height_mm: h };
  };

  const handleApplyCustom = () => {
    commitCustomDims();
    setTimeout(() => onApply(), 10);
  };

  return (
    <section className="panel carton-bar">
      <header className="panel-head" style={{ marginBottom: cartonMode === "auto" ? 0 : 12 }}>
        <div>
          <h2>
            Carton Sizing{" "}
            {currentCartonDims && (
              <span className="muted">
                · {currentCartonSku || "Carton"} ({currentCartonDims.length_mm} ×{" "}
                {currentCartonDims.width_mm} × {currentCartonDims.height_mm} mm)
              </span>
            )}
          </h2>
        </div>

        <div className="segmented">
          <button
            type="button"
            className={cartonMode === "auto" ? "is-active" : ""}
            onClick={() => setCartonMode("auto")}
            title="Automatically select the smallest feasible standard carton"
          >
            Auto Optimal
          </button>
          <button
            type="button"
            className={cartonMode === "preset" ? "is-active" : ""}
            onClick={() => setCartonMode("preset")}
            title="Lock packing to a specific standard carton SKU"
          >
            Standard SKU
          </button>
          <button
            type="button"
            className={cartonMode === "custom" ? "is-active" : ""}
            onClick={() => setCartonMode("custom")}
            title="Specify custom warehouse carton dimensions in mm"
          >
            Custom Size
          </button>
        </div>
      </header>

      {cartonMode === "preset" && (
        <div className="carton-sub-row">
          <label className="muted text-sm">Target SKU:</label>
          <select
            className="select carton-sku-select"
            value={selectedCartonSku}
            onChange={(e) => setSelectedCartonSku(e.target.value)}
          >
            {PRESET_CARTONS.map((p) => (
              <option key={p.sku} value={p.sku}>
                {p.label} — {p.dims}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={onApply}
            disabled={loading}
          >
            {loading ? "Packing…" : "Apply Box"}
          </button>
        </div>
      )}

      {cartonMode === "custom" && (
        <div className="carton-sub-row">
          <label className="muted text-sm">Dimensions (L × W × H mm):</label>
          <div className="dims">
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              className="num-input wide"
              value={lenStr}
              placeholder="Length"
              onChange={(e) => setLenStr(e.target.value.replace(/[^0-9]/g, ""))}
              onBlur={commitCustomDims}
            />
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              className="num-input wide"
              value={widthStr}
              placeholder="Width"
              onChange={(e) => setWidthStr(e.target.value.replace(/[^0-9]/g, ""))}
              onBlur={commitCustomDims}
            />
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              className="num-input wide"
              value={heightStr}
              placeholder="Height"
              onChange={(e) => setHeightStr(e.target.value.replace(/[^0-9]/g, ""))}
              onBlur={commitCustomDims}
            />
          </div>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={handleApplyCustom}
            disabled={loading}
          >
            {loading ? "Packing…" : "Apply Size"}
          </button>
        </div>
      )}
    </section>
  );
};
