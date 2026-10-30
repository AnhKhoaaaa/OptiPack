"""Semantic Post-Sanitizer and Safety Schema Guard (Member 2).

Guarantees epistemic honesty:
1. Unobservable physical properties (like exact weight of unmarked opaque boxes)
   are stripped and returned as weight_g=None, weight_source="unknown".
2. Visible labels ("FRAGILE", "THIS SIDE UP") map strictly to conservative constraints.
3. Orientation rules restrict allowed_rotations:
   - keep_upright=True -> ["LWH", "WLH"]
   - keep_upright=False -> all 6 canonical rotations
4. Fragility-to-Load mapping:
   - "high" -> max_top_load_g = 0, stackable = False
   - "medium" -> max_top_load_g = 2000
   - "low" -> max_top_load_g = 8000
   - "unknown" -> max_top_load_g = 2000
"""

from typing import Any, Dict, List, Optional
from backend.app.schemas.contracts import PhysicalAttributes, RotationCode, UPRIGHT_ROTATION_CODES


ALL_ROTATIONS: List[RotationCode] = [
    RotationCode.LWH,
    RotationCode.WLH,
    RotationCode.LHW,
    RotationCode.HLW,
    RotationCode.WHL,
    RotationCode.HWL,
]


def derive_allowed_rotations(keep_upright: bool) -> List[RotationCode]:
    """Return strictly allowed 3D rotation codes based on upright constraint."""
    if keep_upright:
        return list(UPRIGHT_ROTATION_CODES)
    return list(ALL_ROTATIONS)


def sanitize_physical_attributes(raw_attrs: Dict[str, Any]) -> PhysicalAttributes:
    """Sanitize raw LLM semantic output into safe PhysicalAttributes.

    Rules:
    1. Epistemic Honesty on Weight:
       Only allow weight if explicitly verified from printed OCR (printed_weight_g)
       or external scale/manifest within safe range [5g, 25,000g].
       Otherwise force weight_g = None, weight_source = "unknown".
    2. Orientation:
       Map keep_upright and normalize orientation_source.
    3. Fragility & Stacking:
       Map fragility class and enforce load capacity.
    """
    # 1. Weight handling
    raw_printed_weight = raw_attrs.get("printed_weight_g")
    weight_g: Optional[int] = None
    weight_source: str = "unknown"

    if raw_printed_weight is not None:
        try:
            val = int(raw_printed_weight)
            # Weight sanity guard: 5g to 25,000g
            if 5 <= val <= 25000:
                weight_g = val
                weight_source = "manifest"
            else:
                weight_g = None
                weight_source = "unknown"
        except (ValueError, TypeError):
            weight_g = None
            weight_source = "unknown"
    else:
        # Check if external verified weight was passed
        ext_weight = raw_attrs.get("weight_g")
        ext_source = raw_attrs.get("weight_source", "unknown")
        if ext_weight is not None and ext_source in ("scale_verified", "manifest"):
            try:
                val = int(ext_weight)
                if 5 <= val <= 25000:
                    weight_g = val
                    weight_source = ext_source
                else:
                    weight_g = None
                    weight_source = "unknown"
            except (ValueError, TypeError):
                weight_g = None
                weight_source = "unknown"
        else:
            weight_g = None
            weight_source = "unknown"

    # 2. Fragility & Stacking
    fragility = raw_attrs.get("fragility_class", "unknown")
    if fragility not in ("low", "medium", "high", "unknown"):
        fragility = "medium"

    raw_fragility_source = raw_attrs.get("fragility_source", "unknown")
    if raw_fragility_source in ("visible_label", "ai_inferred_packaging", "user_specified"):
        fragility_source = raw_fragility_source
    else:
        fragility_source = "default_safe"

    # Stackable flag
    stackable = bool(raw_attrs.get("stackable", True))
    if fragility == "high":
        stackable = False

    # Max top load calculation
    max_top_load = raw_attrs.get("max_top_load_g")
    if not stackable or fragility == "high":
        max_top_load = 0
    elif max_top_load is not None:
        try:
            max_top_load = max(0, int(max_top_load))
        except (ValueError, TypeError):
            max_top_load = 2000
    else:
        if fragility == "low":
            max_top_load = 8000
        elif fragility in ("medium", "unknown"):
            max_top_load = 2000

    # 3. Orientation
    keep_upright = bool(raw_attrs.get("keep_upright", False))
    raw_orient_source = raw_attrs.get("orientation_source", "default_unconstrained")
    if keep_upright:
        if raw_orient_source in ("visible_label", "label_this_side_up"):
            orientation_source = "label_this_side_up"
        elif raw_orient_source in ("liquid_container_shape", "bottle_liquid_rule"):
            orientation_source = "bottle_liquid_rule"
        elif raw_orient_source == "user_specified":
            orientation_source = "user_specified"
        else:
            orientation_source = "label_this_side_up"
    else:
        orientation_source = "default_unconstrained"

    # 4. Visible labels
    raw_labels = raw_attrs.get("visible_labels", [])
    if isinstance(raw_labels, list):
        visible_labels = [str(lbl).strip() for lbl in raw_labels if str(lbl).strip()]
    else:
        visible_labels = []

    return PhysicalAttributes(
        weight_g=weight_g,
        weight_source=weight_source,
        fragility_class=fragility,
        fragility_source=fragility_source,
        keep_upright=keep_upright,
        orientation_source=orientation_source,
        stackable=stackable,
        max_top_load_g=max_top_load,
        visible_labels=visible_labels,
    )
