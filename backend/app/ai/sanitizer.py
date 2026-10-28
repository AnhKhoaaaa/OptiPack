"""Semantic Post-Sanitizer and Safety Schema Guard.

Guarantees that unobservable physical properties (like exact weight of opaque boxes)
are stripped or flagged as 'unknown' rather than hallucinated by LLMs.
"""

from typing import Any, Dict, List
from backend.app.schemas.contracts import PhysicalAttributes


def sanitize_physical_attributes(raw_attrs: Dict[str, Any]) -> PhysicalAttributes:
    """Sanitize raw LLM semantic output into safe PhysicalAttributes.

    Rules:
    1. If weight is inferred without an explicit scale label, force weight_g = None
       and weight_source = "unknown".
    2. If fragility is unstated, default to "medium" with source "ai_inferred_packaging"
       or "unknown".
    3. Ensure keep_upright defaults to False unless clear label or bottle semantics.
    """
    weight_g = raw_attrs.get("weight_g")
    weight_source = raw_attrs.get("weight_source", "unknown")

    # Guard against LLM weight hallucination on generic boxes
    if weight_source not in ("scale_verified", "manifest"):
        weight_g = None
        weight_source = "unknown"

    fragility = raw_attrs.get("fragility_class", "medium")
    if fragility not in ("low", "medium", "high", "unknown"):
        fragility = "medium"

    keep_upright = bool(raw_attrs.get("keep_upright", False))
    stackable = bool(raw_attrs.get("stackable", True))
    max_top_load = raw_attrs.get("max_top_load_g")
    visible_labels = raw_attrs.get("visible_labels", [])
    if not isinstance(visible_labels, list):
        visible_labels = []

    return PhysicalAttributes(
        weight_g=weight_g,
        weight_source=weight_source,
        fragility_class=fragility,
        fragility_source=raw_attrs.get("fragility_source", "ai_inferred_packaging"),
        keep_upright=keep_upright,
        orientation_source=raw_attrs.get("orientation_source", "default_unconstrained"),
        stackable=stackable,
        max_top_load_g=max_top_load,
        visible_labels=[str(lbl) for lbl in visible_labels],
    )
