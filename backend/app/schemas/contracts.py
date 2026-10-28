"""OptiPack Canonical Data Contracts (Contract v1.0.0).

This module defines the frozen Pydantic schemas for cross-module communication:
- OrderAnalysisResponse (from CV and AI pipeline)
- PackingRequest (sent to OR solver)
- PackingSolutionResponse (returned by solver and rendered by 3D frontend)

All units conform strictly to 01_PROJECT_SPEC.md:
- Dimensions and positions: Millimeters (int)
- Weight: Grams (int or None)
- Currency: USD (float)
- Time: Milliseconds (int)
- Coordinates: Right-Handed, Z-Up Cartesian system
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Common Geometry & Attribute Types
# -----------------------------------------------------------------------------

class RotationCode(str, Enum):
    """The 6 canonical orthogonal rotations for axis-aligned bounding boxes."""
    LWH = "LWH"
    WLH = "WLH"
    LHW = "LHW"
    HLW = "HLW"
    WHL = "WHL"
    HWL = "HWL"


UPRIGHT_ROTATION_CODES: List[RotationCode] = [RotationCode.LWH, RotationCode.WLH]


class Dimensions3D(BaseModel):
    """Integer millimeter bounding dimensions."""
    length_mm: int = Field(..., gt=0, description="Length along canonical X axis in mm")
    width_mm: int = Field(..., gt=0, description="Width along canonical Y axis in mm")
    height_mm: int = Field(..., gt=0, description="Height along canonical Z axis in mm")


class PlacedDimensions3D(BaseModel):
    """Placed item box extents along carton axes (dx, dy, dz in mm)."""
    dx: int = Field(..., gt=0, description="Span along carton X axis in mm")
    dy: int = Field(..., gt=0, description="Span along carton Y axis in mm")
    dz: int = Field(..., gt=0, description="Span along carton Z axis in mm")


class Position3D(BaseModel):
    """Minimum corner (Front-Left-Bottom) coordinates inside the carton."""
    x: int = Field(..., ge=0, description="X coordinate in mm")
    y: int = Field(..., ge=0, description="Y coordinate in mm")
    z: int = Field(..., ge=0, description="Z coordinate in mm")


class CenterOfMass3D(BaseModel):
    """Center of mass coordinates in mm."""
    x: float = Field(..., description="Center of mass X in mm")
    y: float = Field(..., description="Center of mass Y in mm")
    z: float = Field(..., description="Center of mass Z in mm")


# -----------------------------------------------------------------------------
# Analysis Pipeline Schemas (Endpoint 1: POST /api/v1/orders/analyze)
# -----------------------------------------------------------------------------

class CalibrationInfo(BaseModel):
    """Camera calibration status and fiducial reference metrics."""
    status: Literal["calibrated", "uncalibrated", "fallback_zenith_only"] = Field(
        ..., description="Calibration pipeline execution state"
    )
    reference_type: str = Field("a4_aruco_4corner", description="Type of fiducial marker sheet used")
    detected_markers_count: int = Field(..., ge=0, le=4, description="Count of detected ArUco markers")
    reprojection_error_px: float = Field(..., ge=0.0, description="Reprojection error in pixels")
    scale_mm_per_px_at_z0: float = Field(..., gt=0.0, description="Planar scale factor at table plane Z=0")
    camera_pose_valid: bool = Field(..., description="True if solvePnP yielded physically plausible pose")
    warnings: List[str] = Field(default_factory=list, description="Calibration warning messages")


class ItemUncertainty(BaseModel):
    """Measurement uncertainty and conservative safety margin in mm."""
    length_sigma_mm: float = Field(..., ge=0.0, description="1-sigma standard uncertainty along length")
    width_sigma_mm: float = Field(..., ge=0.0, description="1-sigma standard uncertainty along width")
    height_sigma_mm: float = Field(..., ge=0.0, description="1-sigma standard uncertainty along height")
    safety_margin_mm: int = Field(..., ge=0, description="Inflation margin added for packing clearance")


class MeasurementProvenance(BaseModel):
    """Provenance and confidence tracking for physical dimensions."""
    xy_method: str = Field(..., description="Method used to compute footprint (e.g. aruco_plane_raycast)")
    z_method: str = Field(..., description="Method used to compute height (e.g. dual_view_pnp_triangulation)")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Composite measurement confidence (0-1)")
    requires_user_review: bool = Field(..., description="Flag set true if uncertainty exceeds threshold")


class PhysicalAttributes(BaseModel):
    """Packaging, handling, and load-bearing semantics extracted via AI."""
    weight_g: Optional[int] = Field(None, ge=1, description="Item weight in grams, null if unobservable")
    weight_source: Literal["scale_verified", "manifest", "ai_density_estimate", "unknown"] = "unknown"
    fragility_class: Literal["low", "medium", "high", "unknown"] = "unknown"
    fragility_source: Literal["visible_label", "ai_inferred_packaging", "user_specified", "default_safe"] = "default_safe"
    keep_upright: bool = Field(False, description="Strict upright constraint if true")
    orientation_source: Literal["label_this_side_up", "bottle_liquid_rule", "user_specified", "default_unconstrained"] = "default_unconstrained"
    stackable: bool = Field(True, description="True if other items may be placed on top")
    max_top_load_g: Optional[int] = Field(None, ge=0, description="Maximum downward load tolerated in grams")
    visible_labels: List[str] = Field(default_factory=list, description="Detected labels (e.g. Fragile, CE)")


class VisualEvidence(BaseModel):
    """Cropped image asset and 2D bounding polygon for UI inspection."""
    bbox_2d_px: List[int] = Field(..., min_length=4, max_length=4, description="[x_min, y_min, x_max, y_max]")
    crop_url: Optional[str] = Field(None, description="URL or asset path to the cropped item image")
    mask_rle: Optional[str] = Field(None, description="Run-length encoded binary segmentation mask")
    display_color_hex: str = Field("#3B82F6", description="Assigned UI color for this item")


class DetectedItemMeasurement(BaseModel):
    """Single item detected and measured by CV and AI pipeline."""
    item_id: str = Field(..., description="Unique identifier for item in order (e.g. item_01)")
    display_name: str = Field(..., description="Human-readable label or inferred category name")
    category: str = Field("general_box", description="Inferred product or packaging category")
    quantity: int = Field(1, ge=1, description="Item count")
    dimensions_mm: Dimensions3D = Field(..., description="Estimated nominal bounding box dimensions")
    uncertainty_mm: ItemUncertainty = Field(..., description="Uncertainty quantification")
    measurement_provenance: MeasurementProvenance = Field(..., description="Method provenance and confidence")
    physical_attributes: PhysicalAttributes = Field(default_factory=PhysicalAttributes)
    allowed_rotations: List[RotationCode] = Field(
        default_factory=lambda: [r for r in RotationCode],
        description="Allowed rotation codes for solver placement"
    )
    visual_evidence: VisualEvidence = Field(..., description="Visual debug bounding box and crop info")


class AITelemetry(BaseModel):
    """Telemetry from Meta Model API calls."""
    sam_status: Literal["success", "skipped", "fallback", "failed"] = "skipped"
    muse_model: str = "muse-spark-1.3"
    muse_status: Literal["success", "cached", "fallback", "failed"] = "success"
    muse_latency_ms: int = Field(..., ge=0, description="API latency in milliseconds")
    fallback_activated: bool = False


class OrderAnalysisResponse(BaseModel):
    """Complete response payload for POST /api/v1/orders/analyze."""
    contract_version: str = "1.0.0"
    analysis_id: str = Field(..., description="Unique order analysis identifier")
    timestamp_utc: str = Field(..., description="ISO 8601 UTC timestamp")
    calibration: CalibrationInfo
    items: List[DetectedItemMeasurement]
    ai_telemetry: AITelemetry
    global_warnings: List[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Solver Schemas (Endpoint 2: POST /api/v1/orders/pack)
# -----------------------------------------------------------------------------

class SolverConfig(BaseModel):
    """Configuration passed to the 3D Bin Packing and Cartonization solver."""
    mode: Literal["cpsat_with_heuristic_fallback", "extreme_point_only", "cpsat_exact_only"] = "cpsat_with_heuristic_fallback"
    time_limit_ms: int = Field(3000, ge=100, le=10000, description="Solver time budget in milliseconds")
    apply_uncertainty_margin: bool = Field(True, description="Inflate item dimensions by safety_margin_mm")
    min_support_ratio: float = Field(0.60, ge=0.0, le=1.0, description="Minimum base support area ratio")
    allow_multi_carton_split: bool = Field(True, description="Allow splitting order if single box cannot fit")


class PackableItem(BaseModel):
    """User-verified packable item sent to POST /api/v1/orders/pack."""
    item_id: str = Field(..., description="Unique item identifier matching analysis")
    display_name: str = Field(..., description="Item display name")
    quantity: int = Field(1, ge=1)
    dimensions_mm: Dimensions3D = Field(..., description="Nominal dimensions in mm")
    safety_margin_mm: int = Field(5, ge=0, description="Safety margin added to dimensions")
    weight_g: Optional[int] = Field(None, ge=1, description="Weight in grams, null triggers density fallback")
    weight_assumed: bool = Field(False, description="True if weight is an unconfirmed fallback estimate")
    fragility_class: Literal["low", "medium", "high", "unknown"] = "medium"
    keep_upright: bool = Field(False, description="If true, restricts orientations to LWH and WLH")
    stackable: bool = Field(True, description="If false, no other item can be stacked on top")
    max_top_load_g: Optional[int] = Field(None, ge=0, description="Maximum downward load tolerated")
    allowed_rotations: List[RotationCode] = Field(
        default_factory=lambda: [r for r in RotationCode]
    )
    display_color_hex: str = Field("#3B82F6", description="Hex color code for 3D visualization")


class PackingRequest(BaseModel):
    """Request payload for POST /api/v1/orders/pack."""
    contract_version: str = "1.0.0"
    analysis_id: str = Field(..., description="Associated analysis identifier")
    solver_config: SolverConfig = Field(default_factory=SolverConfig)
    items: List[PackableItem]


# -----------------------------------------------------------------------------
# Packing Solution & Validation Schemas
# -----------------------------------------------------------------------------

class CartonSpec(BaseModel):
    """Standard carton definition from catalog."""
    carton_id: str = Field(..., description="Carton SKU code (e.g. BOX-M)")
    display_name: str = Field(..., description="Human-readable carton name")
    internal_dimensions_mm: Dimensions3D = Field(..., description="Usable internal dimensions")
    tare_weight_g: int = Field(..., ge=0, description="Empty box tare weight in grams")
    max_payload_g: int = Field(..., gt=0, description="Maximum payload capacity in grams")
    box_cost_usd: float = Field(..., ge=0.0, description="Unit cost of corrugated packaging box")


class PlacedItem(BaseModel):
    """A single placed item inside the carton coordinate system."""
    step_number: int = Field(..., ge=1, description="Step placement sequence order (1..N)")
    item_id: str = Field(..., description="Unique item ID")
    display_name: str = Field(..., description="Item display name")
    rotation_code: RotationCode = Field(..., description="Orthogonal rotation applied")
    position_mm: Position3D = Field(..., description="Front-Left-Bottom corner (x_min, y_min, z_min)")
    placed_dimensions_mm: PlacedDimensions3D = Field(..., description="Box extent along carton axes with margin")
    nominal_dimensions_mm: PlacedDimensions3D = Field(..., description="True nominal box extent without margin")
    support_ratio: float = Field(..., ge=0.0, le=1.0, description="Fraction of bottom area supported")
    supported_by_item_ids: List[str] = Field(default_factory=list, description="IDs of items directly supporting this")
    display_color_hex: str = Field("#3B82F6", description="Hex color code for rendering")


class ValidationReport(BaseModel):
    """Independent deterministic geometric & physical constraint validation."""
    is_valid: bool = Field(..., description="True if all geometric and physical checks passed")
    boundary_check_passed: bool = Field(..., description="Zero containment boundary violations")
    overlap_check_passed: bool = Field(..., description="Zero pairwise AABB intersections")
    rotation_check_passed: bool = Field(..., description="All rotations are permitted by item constraints")
    support_check_passed: bool = Field(..., description="All elevated items meet min support ratio")
    fragility_check_passed: bool = Field(..., description="No heavy item placed atop fragile item")
    weight_check_passed: bool = Field(..., description="Total payload does not exceed max_payload_g")
    violations: List[str] = Field(default_factory=list, description="Actionable failure reasons if any")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warning notices")


class PackingMetrics(BaseModel):
    """Financial, volumetric, and physical packing scorecard."""
    volume_utilization_pct: float = Field(..., ge=0.0, le=100.0, description="Packed item volume / carton volume")
    total_items_packed: int = Field(..., ge=0, description="Count of successfully placed items")
    actual_gross_weight_kg: float = Field(..., ge=0.0, description="Gross weight (items + tare) in kg")
    dim_weight_kg: float = Field(..., ge=0.0, description="Dimensional weight in kg")
    billable_weight_kg: float = Field(..., ge=0.0, description="Billable weight tier in kg")
    box_cost_usd: float = Field(..., ge=0.0, description="Carton material cost in USD")
    void_fill_cost_usd: float = Field(..., ge=0.0, description="Estimated void filling paper/pillow cost")
    shipping_cost_usd: float = Field(..., ge=0.0, description="Carrier base + tier shipping fee")
    total_estimated_cost_usd: float = Field(..., ge=0.0, description="Total packaging + shipping cost in USD")
    center_of_mass_mm: CenterOfMass3D = Field(..., description="Estimated composite center of mass")


class PackingPlan(BaseModel):
    """A feasible packing arrangement for a single carton."""
    plan_index: int = Field(1, ge=1, description="Index of this carton plan (1 for primary)")
    carton: CartonSpec = Field(..., description="Selected carton")
    metrics: PackingMetrics = Field(..., description="Financial & volumetric metrics")
    placements: List[PlacedItem] = Field(..., description="Step-by-step placement instructions")
    validation: ValidationReport = Field(..., description="Independent validator findings")


class CandidateCartonEvaluation(BaseModel):
    """Summary of candidate carton feasibility evaluated during cartonization."""
    carton_id: str = Field(..., description="Carton SKU")
    feasible: bool = Field(..., description="True if all items can be packed")
    total_estimated_cost_usd: Optional[float] = Field(None, description="Estimated total cost if feasible")
    volume_utilization_pct: Optional[float] = Field(None, description="Volume utilization if feasible")
    selected: Optional[bool] = Field(False, description="True if this candidate was selected as optimal")
    rejection_reason: Optional[str] = Field(None, description="Explanation if rejected or infeasible")


class PackingSolutionResponse(BaseModel):
    """Complete response payload for POST /api/v1/orders/pack."""
    contract_version: str = "1.0.0"
    status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "TIMEOUT_FALLBACK"] = "OPTIMAL"
    solver_used: str = Field("ortools_cpsat", description="Solver engine name")
    solve_time_ms: int = Field(..., ge=0, description="Wall clock solve time in ms")
    single_carton_feasible: bool = Field(True, description="True if all items fit into 1 carton")
    primary_plan: Optional[PackingPlan] = Field(None, description="Plan for the selected primary carton")
    overflow_plans: List[PackingPlan] = Field(default_factory=list, description="Additional cartons if split")
    unpacked_item_ids: List[str] = Field(default_factory=list, description="Items that could not be packed")
    infeasibility_diagnostics: Optional[Dict[str, Any]] = None
    candidate_carton_comparison: List[CandidateCartonEvaluation] = Field(default_factory=list)
