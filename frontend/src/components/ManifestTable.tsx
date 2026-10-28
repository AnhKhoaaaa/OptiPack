import React from "react";
import { PackableItem, RotationCode } from "../types/contract";

interface ManifestTableProps {
  items: PackableItem[];
  onUpdateItem: (index: number, updated: PackableItem) => void;
  onPackOrder: () => void;
  packingLoading: boolean;
}

export const ManifestTable: React.FC<ManifestTableProps> = ({
  items,
  onUpdateItem,
  onPackOrder,
  packingLoading,
}) => {
  const handleDimensionChange = (
    index: number,
    field: "length_mm" | "width_mm" | "height_mm",
    val: number
  ) => {
    const item = items[index];
    onUpdateItem(index, {
      ...item,
      dimensions_mm: {
        ...item.dimensions_mm,
        [field]: Math.max(10, val),
      },
    });
  };

  const handleWeightChange = (index: number, val: number) => {
    const item = items[index];
    onUpdateItem(index, {
      ...item,
      weight_g: Math.max(1, val),
      weight_assumed: false,
    });
  };

  const handleUprightToggle = (index: number, checked: boolean) => {
    const item = items[index];
    const allowed: RotationCode[] = checked
      ? ["LWH", "WLH"]
      : ["LWH", "WLH", "LHW", "HLW", "WHL", "HWL"];
    onUpdateItem(index, {
      ...item,
      keep_upright: checked,
      allowed_rotations: allowed,
    });
  };

  return (
    <div className="card manifest-card">
      <div className="card-header">
        <h2>2. Detected Items Manifest & Verification</h2>
        <span className="badge badge-accent">{items.length} Items Detected</span>
      </div>

      <p className="card-desc">
        Review detected 3D bounding dimensions and AI handling flags. Items with high measurement uncertainty or assumed weight are highlighted for 1-click confirmation.
      </p>

      <div className="table-responsive">
        <table className="manifest-table">
          <thead>
            <tr>
              <th>Color</th>
              <th>Item Name</th>
              <th>L × W × H (mm)</th>
              <th>Weight (g)</th>
              <th>Keep Upright</th>
              <th>Fragility</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => (
              <tr key={item.item_id}>
                <td>
                  <span
                    className="color-dot"
                    style={{ backgroundColor: item.display_color_hex }}
                  />
                </td>
                <td>
                  <div className="item-title">{item.display_name}</div>
                  <div className="item-id">{item.item_id}</div>
                </td>
                <td>
                  <div className="dim-inputs">
                    <input
                      type="number"
                      value={item.dimensions_mm.length_mm}
                      onChange={(e) =>
                        handleDimensionChange(idx, "length_mm", parseInt(e.target.value) || 0)
                      }
                      title="Length (mm)"
                    />
                    <span>×</span>
                    <input
                      type="number"
                      value={item.dimensions_mm.width_mm}
                      onChange={(e) =>
                        handleDimensionChange(idx, "width_mm", parseInt(e.target.value) || 0)
                      }
                      title="Width (mm)"
                    />
                    <span>×</span>
                    <input
                      type="number"
                      value={item.dimensions_mm.height_mm}
                      onChange={(e) =>
                        handleDimensionChange(idx, "height_mm", parseInt(e.target.value) || 0)
                      }
                      title="Height (mm)"
                    />
                  </div>
                </td>
                <td>
                  <div className="weight-cell">
                    <input
                      type="number"
                      value={item.weight_g || ""}
                      placeholder="Est. 520"
                      onChange={(e) =>
                        handleWeightChange(idx, parseInt(e.target.value) || 0)
                      }
                    />
                    {item.weight_assumed && (
                      <span className="badge badge-warning" title="Density fallback estimate">
                        Assumed
                      </span>
                    )}
                  </div>
                </td>
                <td>
                  <label className="toggle-switch">
                    <input
                      type="checkbox"
                      checked={item.keep_upright}
                      onChange={(e) => handleUprightToggle(idx, e.target.checked)}
                    />
                    <span className="toggle-slider"></span>
                  </label>
                </td>
                <td>
                  <select
                    value={item.fragility_class}
                    onChange={(e) =>
                      onUpdateItem(idx, {
                        ...item,
                        fragility_class: e.target.value as any,
                      })
                    }
                    className="select-fragility"
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High (Fragile)</option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="btn-group manifest-actions">
        <button
          className="btn btn-success btn-lg"
          onClick={onPackOrder}
          disabled={packingLoading || items.length === 0}
        >
          {packingLoading ? "Optimizing Packing & Cost..." : "Optimize Carton & Pack (CP-SAT)"}
        </button>
      </div>
    </div>
  );
};
