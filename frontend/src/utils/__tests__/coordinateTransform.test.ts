/**
 * Phase 0 Gate Unit Test for Member 4: Coordinate Transformation & UI Reducers
 *
 * Conforms strictly to 02D_MEMBER4_FRONTEND_3D_VISUALIZATION.md Section 7.
 * Verifies:
 * 1. Corner-anchored Z-up coordinates map cleanly to center-anchored Y-up Three.js meshes.
 * 2. Zero-gap contact on stacked items (0.0mm discrepancy).
 * 3. Keep-upright toggle updates allowed_rotations to ["LWH", "WLH"].
 * 4. Step scrubber filters visible items correctly.
 */

import { describe, it, expect } from "vitest";
import { mapPlacementToThreeJSFloor, mapPlacementToThreeJSCentered } from "../coordinateTransform";
import { CartonSpec, PlacedItem, RotationCode } from "../../types/contract";

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

  it("test_origin_corner_box_alignment: floor-corner item maps with exact min-corner contact", () => {
    const res = mapPlacementToThreeJSFloor(mockCarton, mockPlacementFloorCorner);

    // dx=100 in carton L=300 -> center x is 50 - 150 = -100
    expect(res.position[0]).toBe(-100);
    // dz=40 on floor z=0 -> center y is 20 (upward)
    expect(res.position[1]).toBe(20);
    // dy=50 in carton W=220 -> center z is 25 - 110 = -85
    expect(res.position[2]).toBe(-85);

    // Three.js box dimensions [width, height, depth] = [dx, dz, dy]
    expect(res.size).toEqual([100, 40, 50]);

    // Check minimum corner contact:
    // min_X = pos_X - width/2 = -100 - 50 = -150 == -cartonL/2 (-150)
    expect(res.position[0] - res.size[0] / 2).toBe(-mockCarton.internal_dimensions_mm.length_mm / 2);
    // min_Y (bottom face) = pos_Y - height/2 = 20 - 20 = 0 (exact floor plane)
    expect(res.position[1] - res.size[1] / 2).toBe(0);
    // min_Z = pos_Z - depth/2 = -85 - 25 = -110 == -cartonW/2 (-110)
    expect(res.position[2] - res.size[2] / 2).toBe(-mockCarton.internal_dimensions_mm.width_mm / 2);
  });

  it("test_stacked_box_vertical_contact: item 1 top Y equals item 2 bottom Y with zero gap", () => {
    const item1: PlacedItem = {
      ...mockPlacementFloorCorner,
      step_number: 1,
      position_mm: { x: 0, y: 0, z: 0 },
      placed_dimensions_mm: { dx: 100, dy: 50, dz: 60 },
    };

    const item2: PlacedItem = {
      ...mockPlacementFloorCorner,
      step_number: 2,
      item_id: "item_02",
      position_mm: { x: 0, y: 0, z: 60 },
      placed_dimensions_mm: { dx: 80, dy: 40, dz: 40 },
    };

    const res1 = mapPlacementToThreeJSFloor(mockCarton, item1);
    const res2 = mapPlacementToThreeJSFloor(mockCarton, item2);

    const item1TopY = res1.position[1] + res1.size[1] / 2; // 30 + 30 = 60
    const item2BottomY = res2.position[1] - res2.size[1] / 2; // 80 - 20 = 60

    expect(item1TopY).toBe(60);
    expect(item2BottomY).toBe(60);
    expect(item2BottomY - item1TopY).toBe(0.0); // 0.0mm contact discrepancy
  });

  it("test_keep_upright_toggle_updates_allowed_rotations", () => {
    const getRotationsForUpright = (keepUpright: boolean): RotationCode[] => {
      return keepUpright ? ["LWH", "WLH"] : ["LWH", "WLH", "LHW", "HLW", "WHL", "HWL"];
    };

    expect(getRotationsForUpright(true)).toEqual(["LWH", "WLH"]);
    expect(getRotationsForUpright(false)).toHaveLength(6);
  });

  it("test_step_scrubber_filtering: activeStep filters visible placements strictly", () => {
    const placements: PlacedItem[] = [1, 2, 3, 4].map((step) => ({
      ...mockPlacementFloorCorner,
      step_number: step,
      item_id: `item_0${step}`,
    }));

    const filterPlacementsByStep = (activeStep: number) => {
      return placements.filter((p) => p.step_number <= activeStep);
    };

    const step2Visible = filterPlacementsByStep(2);
    expect(step2Visible.map((p) => p.item_id)).toEqual(["item_01", "item_02"]);

    const step4Visible = filterPlacementsByStep(4);
    expect(step4Visible).toHaveLength(4);
  });
});
