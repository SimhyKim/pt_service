"""Humanreadable cluster titles from TF-IDF terms"""

from __future__ import annotations


def build_cluster_name(terms: list[str], *, max_terms: int = 4, placeholder: str = "#") -> str:
    """
    Trying to compose a short label from top n-grams like ``kernel | out of | memory``
    instead of only cluster id's
    """
    parts: list[str] = []
    for t in terms[:max_terms]:
        t = (t or "").strip()
        if not t:
            continue
        t = t.replace("<num>", placeholder)
        parts.append(t)
    if not parts:
        return "unnamed"
    return " | ".join(parts)


def normalize_cluster_display_name(label: str) -> str:
    """Normalize legacy labels from metadata that used middle-dot separators."""
    if not label:
        return label
    s = label.replace("\u00b7", " | ").replace(" · ", " | ")
    while " |  | " in s:
        s = s.replace(" |  | ", " | ")
    return s.strip()
