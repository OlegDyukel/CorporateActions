from __future__ import annotations

"""
Effective-date candidate resolver.

Single responsibility: take candidate estimates from various sources (LLM on the
primary filing, follow-up SEC filings, etc.), rank them, and produce:
- extras patch for CorporateAction.extras
- an optional definitive date to set on the model (policy-driven)

The resolver itself never mutates the CorporateAction.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
import os


KIND_ORDER = {
    "definitive": 3,
    "estimated": 2,
    "window": 1,
    "relative": 0,
}


@dataclass
class ResolvePolicy:
    min_confidence: float = 0.85

    @classmethod
    def from_env(cls) -> "ResolvePolicy":
        try:
            min_c = float(os.getenv("LLM_DATE_MIN_CONFIDENCE", "0.85"))
        except Exception:
            min_c = 0.85
        return cls(min_confidence=min_c)


def _norm_kind(kind: Optional[str]) -> str:
    k = (kind or "").strip().lower()
    return k if k in KIND_ORDER else "relative"


def _score(candidate: Dict[str, Any]) -> Tuple[int, float]:
    kind = _norm_kind(candidate.get("kind"))
    conf = float(candidate.get("confidence") or 0.0)
    return (KIND_ORDER.get(kind, 0), conf)


def _normalize_candidate(c: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure only known keys exist; keep any extra keys (e.g., source_url) for transparency
    c = dict(c)
    c["kind"] = _norm_kind(c.get("kind"))
    # Normalize confidence
    try:
        if c.get("confidence") is not None:
            c["confidence"] = float(c["confidence"])
    except Exception:
        c["confidence"] = None
    return c


def resolve_effective_date(
    *,
    candidates: List[Dict[str, Any]],
    policy: Optional[ResolvePolicy] = None,
) -> Tuple[Optional[date], Dict[str, Any]]:
    """Rank candidates and build extras patch.

    Returns (definitive_date_to_set, extras_patch).
    - definitive_date_to_set is provided only when the best definitive candidate meets confidence.
    - extras_patch contains `effective_date_candidates` and `effective_date_recommendation`.
    """
    policy = policy or ResolvePolicy.from_env()

    if not candidates:
        return None, {}

    norm: List[Dict[str, Any]] = [_normalize_candidate(c) for c in candidates]

    # Sort by kind then confidence (desc)
    ranked = sorted(norm, key=_score, reverse=True)

    recommendation = None
    for c in ranked:
        recommendation = c
        break

    # Attempt to promote to definitive date if policy allows and candidate is definitive
    definitive_date: Optional[date] = None
    best_definitive = next((c for c in ranked if c.get("kind") == "definitive" and c.get("date")), None)
    if best_definitive and (best_definitive.get("confidence") or 0.0) >= policy.min_confidence:
        definitive_date = best_definitive.get("date")  # type: ignore[assignment]

    extras_patch: Dict[str, Any] = {
        "effective_date_candidates": ranked,
        "effective_date_recommendation": recommendation,
    }

    return definitive_date, extras_patch


def format_estimate_for_display(extras: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return a short human-readable summary, if recommendation exists.

    Examples:
      - "2025-09-30 (LLM, 0.92)"
      - "Q4 2025 (window, 0.75)"
      - "within 60 days after shareholder approval (relative, 0.6)"
    """
    if not extras:
        return None
    rec = extras.get("effective_date_recommendation") if isinstance(extras, dict) else None
    if not rec:
        return None

    kind = rec.get("kind")
    conf = rec.get("confidence")
    method = rec.get("method")
    if rec.get("date"):
        base = str(rec.get("date"))
        meta = ", ".join([x for x in [method, f"{conf:.2f}" if isinstance(conf, (float, int)) else None] if x])
        return f"{base} ({meta})" if meta else base
    if rec.get("start_date") and rec.get("end_date"):
        # Try to recover quarter if qualifier contains it
        qual = rec.get("qualifier") or "window"
        base = qual
        meta = ", ".join([x for x in [method, f"{conf:.2f}" if isinstance(conf, (float, int)) else None] if x])
        return f"{base} ({meta})" if meta else base
    if rec.get("qualifier"):
        base = rec.get("qualifier")
        meta = ", ".join([x for x in [method, f"{conf:.2f}" if isinstance(conf, (float, int)) else None] if x])
        return f"{base} ({meta})" if meta else base
    return None
