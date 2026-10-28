/**
 * 3D Coordinate Transform Adapter (Member 4 - Phase 0 Deliverable)
 *
 * Translates between:
 * - Backend / Solver Canonical Coordinates: Right-Handed, Z-Up, Front-Left-Bottom Corner Origin.
 *   +X: Left-to-Right (Length L)
 *   +Y: Front-to-Back (Width W)
 *   +Z: Upward / against gravity (Height H)
 * - Three.js Coordinates: Y-Up, Center-Anchored BoxGeometry.
 *   +X_three: Left-to-Right
 *   +Y_three: Upward (corresponds to backend +Z)
 *   +Z_three: Depth / Back-to-Front (corresponds to backend +Y)
 */

import { CartonSpec, PlacedItem } from "../types/contract";

export interface ThreeJSTransform {
  /** Center position for Three.js Mesh [x, y, z] */
  position: [number, number, number];
  /** Dimensions for BoxGeometry [width, height, depth] */
  size: [number, number, number];
}

/**
 * Maps a backend placed item into Three.js coordinates with the carton's
 * bottom-center resting on world ground (Y_three = 0).
 */
export function mapPlacementToThreeJSFloor(
  carton: CartonSpec,
  placement: PlacedItem
): ThreeJSTransform {
  const cartonL = carton.internal_dimensions_mm.length_mm;
  const cartonW = carton.internal_dimensions_mm.width_mm;

  const dx = placement.placed_dimensions_mm.dx;
  const dy = placement.placed_dimensions_mm.dy;
  const dz = placement.placed_dimensions_mm.dz;

  const minX = placement.position_mm.x;
  const minY = placement.position_mm.y;
  const minZ = placement.position_mm.z;

  // Center of box relative to carton center on X and Z (depth), with floor at Y = 0
  const threeX = minX + dx / 2.0 - cartonL / 2.0;
  const threeY = minZ + dz / 2.0; // Y is UP in Three.js
  const threeZ = minY + dy / 2.0 - cartonW / 2.0; // Z is depth in Three.js

  return {
    position: [threeX, threeY, threeZ],
    size: [dx, dz, dy], // [width, height, depth]
  };
}

/**
 * Maps a backend placed item into Three.js coordinates with carton centered at (0, 0, 0).
 */
export function mapPlacementToThreeJSCentered(
  carton: CartonSpec,
  placement: PlacedItem
): ThreeJSTransform {
  const cartonL = carton.internal_dimensions_mm.length_mm;
  const cartonW = carton.internal_dimensions_mm.width_mm;
  const cartonH = carton.internal_dimensions_mm.height_mm;

  const dx = placement.placed_dimensions_mm.dx;
  const dy = placement.placed_dimensions_mm.dy;
  const dz = placement.placed_dimensions_mm.dz;

  const minX = placement.position_mm.x;
  const minY = placement.position_mm.y;
  const minZ = placement.position_mm.z;

  const threeX = minX + dx / 2.0 - cartonL / 2.0;
  const threeY = minZ + dz / 2.0 - cartonH / 2.0;
  const threeZ = minY + dy / 2.0 - cartonW / 2.0;

  return {
    position: [threeX, threeY, threeZ],
    size: [dx, dz, dy],
  };
}
