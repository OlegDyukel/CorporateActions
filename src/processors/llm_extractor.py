from __future__ import annotations

"""
LLM-based extraction of corporate action details from filing text.

- Uses OpenAI if OPENAI_API_KEY is provided; otherwise, functions return None and the caller should skip.
- Produces a structured intermediate result (LLMExtractionResult) and a helper to apply it to CorporateAction.

This module is intentionally defensive: if the LLM call or parsing fails, callers get None and continue.
"""

import json
import os
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from src.models.corporate_action_model import (
    ActionType,
    ConsiderationLeg,
    ConsiderationType,
    CorporateAction,
    Money,
    Ratio,
    SecurityRef,
)

# Optional import; the module should still import if OpenAI is missing
try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


class LLMMonetary(BaseModel):
    currency: Optional[str] = None
    amount: Optional[Decimal] = None


class LLMConsiderationLeg(BaseModel):
    type: Optional[str] = Field(None, description="cash | stock | rights | other")
    cash_per_share: Optional[LLMMonetary] = None
    stock_ratio: Optional[str] = None
    stock_security_ticker: Optional[str] = None


class LLMDateEstimate(BaseModel):
    """Represents an estimated effective date candidate extracted by the LLM.

    kind: one of 'definitive' | 'estimated' | 'window' | 'relative'
    - definitive: a specific effective date stated as factual (e.g., "effective on Sep 30, 2025").
    - estimated: a specific target date with hedging (e.g., "on or about Oct 1, 2025").
    - window: a date range or period (e.g., "Q4 2025" -> start/end).
    - relative: relative to another milestone (e.g., "within 60 days after shareholder approval").
    """

    kind: Optional[str] = None
    date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    relative_to: Optional[str] = None
    offset_days: Optional[int] = None
    qualifier: Optional[str] = None
    snippet: Optional[str] = None
    confidence: Optional[float] = None
    # Populated by the pipeline (not the LLM) to link to CorporateAction.sources index
    source_index: Optional[int] = None


class LLMExtractionResult(BaseModel):
    action_type: Optional[str] = None
    announce_date: Optional[date] = None
    effective_date: Optional[date] = None
    ex_date: Optional[date] = None
    record_date: Optional[date] = None
    pay_date: Optional[date] = None
    ratio: Optional[str] = None
    cash_per_share: Optional[LLMMonetary] = None
    consideration: Optional[List[LLMConsiderationLeg]] = None
    notes: Optional[str] = None
    # New: estimates for effective_date when no definitive date is present
    effective_date_estimates: Optional[List[LLMDateEstimate]] = None


def _ratio_from_string(text: Optional[str]) -> Optional[Ratio]:
    """Parse a ratio string into Ratio(numerator, denominator).

    Accepts formats like:
    - "2-for-1", "2 for 1", "1 new for 10 old"
    - "0.5" (interpreted as 0.5 new per 1 old -> 1-for-2)
    - "3:2", "3/2"
    Returns None if parsing fails.
    """
    if not text:
        return None
    s = text.strip().lower()

    # Case: simple decimal (e.g., "0.5")
    try:
        if re.fullmatch(r"\d*\.\d+|\d+", s):
            from fractions import Fraction

            f = Fraction(Decimal(s)).limit_denominator(1000)
            return Ratio(numerator=int(f.numerator), denominator=int(f.denominator))
    except Exception:
        pass

    # Case: patterns like "2-for-1", "2 for 1", "3:2", "3/2"
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-?\s*for\s*-?|:|/)\s*(\d+)", s)
    if m:
        num_str, den_str = m.group(1), m.group(2)
        try:
            from fractions import Fraction

            if "." in num_str:
                f = Fraction(Decimal(num_str)).limit_denominator(1000)
                return Ratio(numerator=int(f.numerator), denominator=int(f.denominator) * int(den_str))
            return Ratio(numerator=int(num_str), denominator=int(den_str))
        except Exception:
            return None

    return None


def _money_from_llm(m: Optional[LLMMonetary]) -> Optional[Money]:
    if not m or m.amount is None or not m.currency:
        return None
    try:
        return Money(currency=m.currency.upper(), amount=Decimal(m.amount))
    except Exception:
        return None


def _consideration_from_llm(legs: Optional[List[LLMConsiderationLeg]]) -> Optional[List[ConsiderationLeg]]:
    if not legs:
        return None
    result: List[ConsiderationLeg] = []
    for leg in legs:
        leg_type = (leg.type or "").lower().strip()
        if leg_type not in {
            ConsiderationType.CASH,
            ConsiderationType.STOCK,
            ConsiderationType.RIGHTS,
            ConsiderationType.OTHER,
        }:
            continue
        cash = _money_from_llm(leg.cash_per_share)
        stock_ratio = _ratio_from_string(leg.stock_ratio) if leg.stock_ratio else None
        stock_sec = (
            SecurityRef(ticker=leg.stock_security_ticker.upper())
            if leg.stock_security_ticker
            else None
        )
        try:
            result.append(
                ConsiderationLeg(
                    type=leg_type,
                    cash_per_share=cash,
                    stock_ratio=stock_ratio,
                    stock_security=stock_sec,
                )
            )
        except Exception:
            # If the leg fails validation (e.g., missing stock_ratio for stock leg), skip it
            continue
    return result or None


@dataclass
class LLMCallConfig:
    enabled: bool
    model: str
    api_key: Optional[str]


def _is_enabled() -> bool:
    return (os.getenv("LLM_ENABLED", "true").strip().lower() in {"1", "true", "yes"})


def _get_config() -> LLMCallConfig:
    return LLMCallConfig(
        enabled=_is_enabled(),
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )


def llm_extract(text: str, *, company: Optional[str] = None) -> Optional[LLMExtractionResult]:
    """Call the LLM to extract corporate action data from raw filing text.

    Returns None if disabled, missing API key, OpenAI not installed, or on error.
    """
    cfg = _get_config()
    if not cfg.enabled:
        return None
    if not cfg.api_key or OpenAI is None:
        return None

    client = OpenAI(api_key=cfg.api_key)

    system = (
        "You are a financial extraction assistant. Read SEC filing text and return a compact JSON with key corporate action details. "
        "If there is no clear corporate action, set action_type to 'other' and leave details null. "
        "Only output valid JSON matching the schema."
    )

    allowed_types = [
        ActionType.FORWARD_SPLIT,
        ActionType.REVERSE_SPLIT,
        ActionType.CASH_DIVIDEND,
        ActionType.STOCK_DIVIDEND,
        ActionType.SPIN_OFF,
        ActionType.MERGER_CASH,
        ActionType.MERGER_STOCK,
        ActionType.MERGER_CASH_STOCK,
        ActionType.RIGHTS_OFFERING,
        ActionType.TENDER_OFFER,
        ActionType.BUYBACK,
        ActionType.BANKRUPTCY,
        ActionType.OTHER,
    ]

    user_prompt = {
        "role": "user",
        "content": (
            f"Company: {company or 'Unknown'}\n\n"
            "Task: Extract the following fields from the filing text.\n"
            "Return ONLY JSON with this structure and keys: \n"
            "{\n"
            "  \"action_type\": one of "
            + json.dumps(allowed_types)
            + ",\n"
            "  \"announce_date\": YYYY-MM-DD or null,\n"
            "  \"effective_date\": YYYY-MM-DD or null,\n"
            "  \"ex_date\": YYYY-MM-DD or null,\n"
            "  \"record_date\": YYYY-MM-DD or null,\n"
            "  \"pay_date\": YYYY-MM-DD or null,\n"
            "  \"ratio\": string like '2-for-1' or '0.5' or null,\n"
            "  \"cash_per_share\": {\"currency\": 'USD', \"amount\": 12.34} or null,\n"
            "  \"consideration\": [\n"
            "    {\n"
            "      \"type\": 'cash'|'stock'|'rights'|'other',\n"
            "      \"cash_per_share\": {\"currency\": 'USD', \"amount\": 12.34} or null,\n"
            "      \"stock_ratio\": '0.5' or '1-for-10' or null,\n"
            "      \"stock_security_ticker\": 'ABC' or null\n"
            "    }\n"
            "  ] or null,\n"
            "  \"effective_date_estimates\": [\n"
            "    {\n"
            "      \"kind\": 'definitive'|'estimated'|'window'|'relative',\n"
            "      \"date\": YYYY-MM-DD or null,\n"
            "      \"start_date\": YYYY-MM-DD or null,\n"
            "      \"end_date\": YYYY-MM-DD or null,\n"
            "      \"relative_to\": short label like 'shareholder_approval' or null,\n"
            "      \"offset_days\": integer number of days if relative, or null,\n"
            "      \"qualifier\": short phrase like 'effective on' or 'expected in Q4 2025',\n"
            "      \"snippet\": <=200-char supporting snippet,\n"
            "      \"confidence\": 0..1 (your best estimate)\n"
            "    }\n"
            "  ] or null,\n"
            "  \"notes\": optional short string\n"
            "}\n\n"
            "If no definitive effective date is present, populate effective_date_estimates with your best candidates, including quarter windows (convert 'Qx YYYY' into start_date/end_date).\n"
            "Filing text begins below.\n\n"
            + text[:20000]  # Trim to keep prompt size reasonable
        ),
    }

    try:
        # Using Chat Completions API for wide compatibility
        resp = client.chat.completions.create(
            model=cfg.model,
            messages=[{"role": "system", "content": system}, user_prompt],
            temperature=0.1,
            max_tokens=800,
        )
        content = resp.choices[0].message.content or "{}"
        # In case the model adds backticks or text, attempt to extract JSON substring
        json_text = _extract_json_block(content)
        data = json.loads(json_text)
        return LLMExtractionResult.model_validate(data)
    except Exception:
        return None


def _extract_json_block(text: str) -> str:
    """Extract a JSON object from free-form text. Fallback to the whole text if already JSON.
    """
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def apply_llm_to_corporate_action(base: CorporateAction, res: LLMExtractionResult) -> CorporateAction:
    """Return a new CorporateAction with LLM-derived fields applied conservatively.

    Strategy:
    - Build Terms first to satisfy validators before switching action_type.
    - Only overwrite fields if the LLM provided a confident-looking value.
    - On any validation error, fall back to returning the original base object.
    """
    try:
        terms = base.terms.model_copy(deep=True)

        # Ratio / cash_per_share
        r = _ratio_from_string(res.ratio) if res.ratio else None
        if r:
            terms.ratio = r
        if res.cash_per_share:
            m = _money_from_llm(res.cash_per_share)
            if m:
                terms.cash_per_share = m

        # Consideration legs
        cons = _consideration_from_llm(res.consideration)
        if cons:
            terms.consideration = cons

        # Date fields
        updated = base.model_copy(
            update={
                "announce_date": res.announce_date or base.announce_date,
                "effective_date": res.effective_date or base.effective_date,
                "ex_date": res.ex_date or base.ex_date,
                "record_date": res.record_date or base.record_date,
                "pay_date": res.pay_date or base.pay_date,
                "terms": terms,
                "extracted_fields_version": "v1-llm",
                "extraction_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            }
        )

        # Action type last (to avoid validator conflicts)
        at = (res.action_type or "").strip() or None
        if at in {v for v in ActionType.__dict__.values() if isinstance(v, str)}:
            updated = updated.model_copy(update={"action_type": at})

        # Append LLM note to provenance notes
        note = (res.notes or "").strip()
        if note:
            merged_note = f"{(updated.notes or '').strip()} | {note}".strip(" |")
            updated = updated.model_copy(update={"notes": merged_note})

        # Force updated_at refresh
        updated = updated.model_copy(update={"updated_at": base.updated_at})
        return updated
    except Exception:
        return base


__all__ = [
    "LLMExtractionResult",
    "LLMDateEstimate",
    "llm_extract",
    "apply_llm_to_corporate_action",
]
