/**
 * OptiPack Canonical TypeScript Interfaces (Contract v1.0.0)
 *
 * Conforms strictly to 01_PROJECT_SPEC.md.
 * All units:
 * - Dimensions / Positions: Millimeters (mm)
 * - Weights: Grams (g) or null
 * - Cost: USD ($)
 * - Latency: Milliseconds (ms)
 */

export type RotationCode = "LWH" | "WLH" | "LHW" | "HLW" | "WHL" | "HWL";

export interface Dimensions3D {
  length_mm: number;
  width_mm: number;
  height_mm: number;
}

export interface PlacedDimensions3D {
  dx: number;
  dy: number;
  dz: number;
}

export interface Position3D {
  x: number;
  y: number;
  z: number;
}

export interface CenterOfMass3D {
  x: number;
  y: number;
  z: number;
}

export interface CalibrationInfo {
  status: "calibrated" | "uncalibrated" | "fallback_zenith_only";
  reference_type: string;
  detected_markers_count: number;
  reprojection_error_px: number;
  scale_mm_per_px_at_z0: number;
  camera_pose_valid: boolean;
  warnings: string[];
}

export interface ItemUncertainty {
  length_sigma_mm: number;
  width_sigma_mm: number;
  height_sigma_mm: number;
  safety_margin_mm: number;
}

export interface MeasurementProvenance {
  xy_method: string;
  z_method: string;
  confidence_score: number;
  requires_user_review: boolean;
}

export interface PhysicalAttributes {
  weight_g: number | null;
  weight_source: "scale_verified" | "manifest" | "ai_density_estimate" | "unknown";
  fragility_class: "low" | "medium" | "high" | "unknown";
  fragility_source: "visible_label" | "ai_inferred_packaging" | "user_specified" | "default_safe";
  keep_upright: boolean;
  orientation_source: "label_this_side_up" | "bottle_liquid_rule" | "user_specified" | "default_unconstrained";
  stackable: boolean;
  max_top_load_g: number | null;
  visible_labels: string[];
}

export interface VisualEvidence {
  bbox_2d_px: [number, number, number, number];
  crop_url: string | null;
  mask_rle: string | null;
  display_color_hex: string;
}

export interface DetectedItemMeasurement {
  item_id: string;
  display_name: string;
  category: string;
  quantity: number;
  dimensions_mm: Dimensions3D;
  uncertainty_mm: ItemUncertainty;
  measurement_provenance: MeasurementProvenance;
  physical_attributes: PhysicalAttributes;
  allowed_rotations: RotationCode[];
  visual_evidence: VisualEvidence;
}

export interface AITelemetry {
  sam_status: "success" | "skipped" | "fallback" | "failed";
  muse_model: string;
  muse_status: "success" | "cached" | "fallback" | "failed";
  muse_latency_ms: number;
  fallback_activated: boolean;
}

export interface OrderAnalysisResponse {
  contract_version: string;
  analysis_id: string;
  timestamp_utc: string;
  calibration: CalibrationInfo;
  items: DetectedItemMeasurement[];
  ai_telemetry: AITelemetry;
  global_warnings: string[];
}

export interface SolverConfig {
  mode: "cpsat_with_heuristic_fallback" | "extreme_point_only" | "cpsat_exact_only";
  time_limit_ms: number;
  apply_uncertainty_margin: boolean;
  min_support_ratio: number;
  allow_multi_carton_split: boolean;
}

export interface PackableItem {
  item_id: string;
  display_name: string;
  quantity: number;
  dimensions_mm: Dimensions3D;
  safety_margin_mm: number;
  weight_g: number | null;
  weight_assumed: boolean;
  fragility_class: "low" | "medium" | "high" | "unknown";
  keep_upright: boolean;
  stackable: boolean;
  max_top_load_g: number | null;
  allowed_rotations: RotationCode[];
  display_color_hex: string;
}

export interface PackingRequest {
  contract_version: string;
  analysis_id: string;
  solver_config: SolverConfig;
  items: PackableItem[];
}

export interface CartonSpec {
  carton_id: string;
  display_name: string;
  internal_dimensions_mm: Dimensions3D;
  tare_weight_g: number;
  max_payload_g: number;
  box_cost_usd: number;
}

export interface PlacedItem {
  step_number: number;
  item_id: string;
  display_name: string;
  rotation_code: RotationCode;
  position_mm: Position3D;
  placed_dimensions_mm: PlacedDimensions3D;
  nominal_dimensions_mm: PlacedDimensions3D;
  support_ratio: number;
  supported_by_item_ids: string[];
  display_color_hex: string;
}

export interface ValidationReport {
  is_valid: boolean;
  boundary_check_passed: boolean;
  overlap_check_passed: boolean;
  rotation_check_passed: boolean;
  support_check_passed: boolean;
  fragility_check_passed: boolean;
  weight_check_passed: boolean;
  violations: string[];
  warnings: string[];
}

export interface PackingMetrics {
  volume_utilization_pct: number;
  total_items_packed: number;
  actual_gross_weight_kg: number;
  dim_weight_kg: number;
  billable_weight_kg: number;
  box_cost_usd: number;
  void_fill_cost_usd: number;
  shipping_cost_usd: number;
  total_estimated_cost_usd: number;
  center_of_mass_mm: CenterOfMass3D;
}

export interface PackingPlan {
  plan_index: number;
  carton: CartonSpec;
  metrics: PackingMetrics;
  placements: PlacedItem[];
  validation: ValidationReport;
}

export interface CandidateCartonEvaluation {
  carton_id: string;
  feasible: boolean;
  total_estimated_cost_usd?: number;
  volume_utilization_pct?: number;
  selected?: boolean;
  rejection_reason?: string;
}

export interface PackingSolutionResponse {
  contract_version: string;
  status: "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "TIMEOUT_FALLBACK";
  solver_used: string;
  solve_time_ms: number;
  single_carton_feasible: boolean;
  primary_plan: PackingPlan | null;
  overflow_plans: PackingPlan[];
  unpacked_item_ids: string[];
  infeasibility_diagnostics?: Record<string, unknown> | null;
  candidate_carton_comparison: CandidateCartonEvaluation[];
}
