from __future__ import annotations

from typing import TypedDict


class UnifiedColor(TypedDict):
    hex: str
    default_label: str
    is_category: bool
    category: str | None


UNIFIED_COLORS: list[UnifiedColor] = [
    {"hex": "#22c55e", "default_label": "Findings", "is_category": True, "category": "findings"},
    {"hex": "#3b82f6", "default_label": "Methods", "is_category": True, "category": "methods"},
    {"hex": "#a855f7", "default_label": "Definitions", "is_category": True, "category": "definitions"},
    {"hex": "#f97316", "default_label": "Limitations", "is_category": True, "category": "limitations"},
    {"hex": "#6b7280", "default_label": "Background", "is_category": True, "category": "background"},
    {"hex": "#FFFF00", "default_label": "Highlights", "is_category": False, "category": None},
    {"hex": "#EF4444", "default_label": "Important", "is_category": False, "category": None},
    {"hex": "#00FFFF", "default_label": "Follow-up", "is_category": False, "category": None},
]

CATEGORY_COLORS: dict[str, str] = {
    c["category"]: c["hex"]
    for c in UNIFIED_COLORS
    if c["is_category"] and c["category"] is not None
}

VALID_ANNOTATION_COLORS: set[str] = {c["hex"] for c in UNIFIED_COLORS}

DEFAULT_HIGHLIGHT_COLOR = "#FFFF00"

DEFAULT_COLOR_LABELS: dict[str, str] = {c["hex"]: c["default_label"] for c in UNIFIED_COLORS}
