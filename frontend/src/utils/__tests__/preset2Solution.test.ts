import { describe, it, expect } from "vitest";
import preset2PackingSolution from "../../mocks/preset2PackingSolution.json";
import { PackingSolutionResponse } from "../../types/contract";

describe("Preset 2 Packing Solution Verification", () => {
  const solution = preset2PackingSolution as unknown as PackingSolutionResponse;

  it("should conform to Contract v1.0.0 structure", () => {
    expect(solution.contract_version).toBe("1.0.0");
    expect(solution.status).toBe("OPTIMAL");
    expect(solution.primary_plan).not.toBeNull();
    if (!solution.primary_plan) return;

    expect(solution.primary_plan.carton.carton_id).toBe("BOX-M");
    expect(solution.primary_plan.placements).toHaveLength(3);
  });

  it("should fit all items within BOX-M dimensions without boundary overflow", () => {
    expect(solution.primary_plan).not.toBeNull();
    if (!solution.primary_plan) return;

    const carton = solution.primary_plan.carton.internal_dimensions_mm;
    solution.primary_plan.placements.forEach((item) => {
      const maxX = item.position_mm.x + item.placed_dimensions_mm.dx;
      const maxY = item.position_mm.y + item.placed_dimensions_mm.dy;
      const maxZ = item.position_mm.z + item.placed_dimensions_mm.dz;

      expect(maxX).toBeLessThanOrEqual(carton.length_mm);
      expect(maxY).toBeLessThanOrEqual(carton.width_mm);
      expect(maxZ).toBeLessThanOrEqual(carton.height_mm);
    });
  });

  it("should have zero overlaps between items", () => {
    expect(solution.primary_plan).not.toBeNull();
    if (!solution.primary_plan) return;

    const items = solution.primary_plan.placements;
    for (let i = 0; i < items.length; i++) {
      for (let j = i + 1; j < items.length; j++) {
        const a = items[i];
        const b = items[j];

        const noOverlapX =
          a.position_mm.x + a.placed_dimensions_mm.dx <= b.position_mm.x ||
          b.position_mm.x + b.placed_dimensions_mm.dx <= a.position_mm.x;

        const noOverlapY =
          a.position_mm.y + a.placed_dimensions_mm.dy <= b.position_mm.y ||
          b.position_mm.y + b.placed_dimensions_mm.dy <= a.position_mm.y;

        const noOverlapZ =
          a.position_mm.z + a.placed_dimensions_mm.dz <= b.position_mm.z ||
          b.position_mm.z + b.placed_dimensions_mm.dz <= a.position_mm.z;

        const separated = noOverlapX || noOverlapY || noOverlapZ;
        expect(separated).toBe(true);
      }
    }
  });
});
