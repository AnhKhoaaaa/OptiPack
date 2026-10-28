/**
 * Phase 0 Gate Unit Test for Member 4: Coordinate Transformation
 *
 * Verifies that corner-anchored Z-up coordinates map cleanly to
 * center-anchored Y-up Three.js meshes with 0.0mm alignment error.
 */

import { mapPlacementToThreeJSFloor, mapPlacementToThreeJSCentered } from "../coordinateTransform";
import { CartonSpec, PlacedItem } from "../../types/contract";

describe("Coordinate Transform Adapter (Member 4 Phase 0 Gate)", () => {
  const mockCarton: CartonSpec = {
    carton_id: "BOX-M",
    display_name: "Medium Standard Carton",
    internal_dimensions_mm: { length_mm: 300, width_mm: 220, height_mm: 150 },
    tare_weight_g: 160,
    max_payload_g: 8000,
    box_cost_usd: 0.85,
  };

  const mockPlacementFloorCorner: PlacedItem = {
    step_number: 1,
    item_id: "item_01",
    display_name: "Test Box",
    rotation_code: "LWH",
    position_mm: { x: 0, y: 0, z: 0 },
    placed_dimensions_mm: { dx: 100, dy: 50, dz: 40 },
    nominal_dimensions_mm: { dx: 95, dy: 45, dz: 35 },
    support_ratio: 1.0,
    supported_by_item_ids: ["CARTON_FLOOR"],
    display_color_hex: "#3B82F6",
  };

  it("should map floor-corner item correctly in floor-anchored Three.js mode", () => {
    const res = mapPlacementToThreeJSFloor(mockCarton, mockPlacementFloorCorner);

    // dx=100 in carton L=300 -> center x is 50 - 150 = -100
    expect(res.position[0]).toBe(-100);
    // dz=40 on floor z=0 -> center y is 20 (upward)
    expect(res.position[1]).toBe(20);
    // dy=50 in carton W=220 -> center z is 25 - 110 = -85
    expect(res.position[2]).toBe(-85);

    // Three.js box dimensions [width, height, depth] = [dx, dz, dy]
    expect(res.size).toEqual([100, 40, 50]);
  });

  it("should map stacked item at z=40 with proper vertical offset", () => {
    const stackedPlacement: PlacedItem = {
      ...mockPlacementFloorCorner,
      step_number: 2,
      item_id: "item_02",
      position_mm: { x: 0, y: 0, z: 40 },
      placed_dimensions_mm: { dx: 80, dy: 40, dz: 30 },
    };

    const res = mapPlacementToThreeJSFloor(mockCarton, stackedPlacement);
    // z=40 + dz/2 = 40 + 15 = 55
    expect(res.position[1]).toBe(55);
    expect(res.size).toEqual([80, 30, 40]);
  });
});
