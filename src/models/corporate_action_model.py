from __future__ import annotations

"""
Corporate Actions schema (Pydantic v2) — production-ready baseline
- Deterministic event_id (UUIDv5) based on identifiers + action + dates + terms
- Enumerations for action types, doc types, sources, status
- Structured consideration breakdown (cash, stock, rights, other)
- Provenance tracking per field
- Validation for dates, tickers, currency, confidence, and terms coherency
"""

from datetime import date, datetime
from decimal import Decimal
import hashlib
import re
import uuid
from typing import Dict, List, Optional, Union, Any

from pydantic import BaseModel, Field, field_validator, model_validator


# -----------------------
# Enumerations
# -----------------------

class ActionType(str):
    """Normalized set of corporate action types.

    Keep this list stable; add new values rather than renaming.
    """

    FORWARD_SPLIT = "forward_split"
    REVERSE_SPLIT = "reverse_split"
    CASH_DIVIDEND = "cash_dividend"
    STOCK_DIVIDEND = "stock_dividend"
    SPIN_OFF = "spin_off"
    MERGER_CASH = "merger_cash"
    MERGER_STOCK = "merger_stock"
    MERGER_CASH_STOCK = "merger_cash_stock"
    RIGHTS_OFFERING = "rights_offering"
    TENDER_OFFER = "tender_offer"
    BUYBACK = "buyback"
    BANKRUPTCY = "bankruptcy"
    OTHER = "other"


class DocType(str):
    EIGHT_K = "8-K"
    SIX_K = "6-K"
    TEN_K = "10-K"
    TEN_Q = "10-Q"
    F_S = "F-**"  # wildcard bucket for foreign forms; keep as string if unknown
    PROSPECTUS = "prospectus"
    EXCHANGE_NOTICE = "exchange_notice"
    PRESS_RELEASE = "press_release"
    COMPANY_ANNOUNCEMENT = "company_announcement"
    REGULATOR_BULLETIN = "regulator_bulletin"
    OTHER = "other"


class SourceSystem(str):
    SEC_EDGAR = "sec_edgar"
    NASDAQ = "nasdaq"
    NYSE = "nyse"
    NIKKEI = "nikkei"
    JPX = "jpx"
    LSE = "lse"
    EURONEXT = "euronext"
    COMPANY_IR = "company_ir"
    NEWSWIRE = "newswire"
    OTHER = "other"


class Status(str):
    ANNOUNCED = "announced"
    AMENDED = "amended"
    WITHDRAWN = "withdrawn"
    EFFECTIVE = "effective"
    CANCELLED = "cancelled"


class ConsiderationType(str):
    CASH = "cash"
    STOCK = "stock"
    RIGHTS = "rights"
    OTHER = "other"


# -----------------------
# Primitives & helpers
# -----------------------

TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,12}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
CUSIP_RE = re.compile(r"^[0-9A-Z]{9}$")
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
CIK_RE = re.compile(r"^[0-9]{10}$")
MIC_RE = re.compile(r"^[A-Z0-9]{4}$")  # ISO 10383


class Money(BaseModel):
    currency: str = Field(..., description="ISO-4217 currency code, e.g., USD")
    amount: Decimal = Field(..., description="Monetary amount per share or absolute, as specified in context")

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        if not CURRENCY_RE.match(v or ""):
            raise ValueError("currency must be 3-letter ISO code, uppercase")
        return v


class Ratio(BaseModel):
    """Represents terms like 2-for-1, or 0.5 new per old.

    Use numerator/denominator to preserve exactness; .as_decimal() gives Decimal.
    """

    numerator: int = Field(..., ge=1)
    denominator: int = Field(..., ge=1)

    def as_decimal(self) -> Decimal:
        return (Decimal(self.numerator) / Decimal(self.denominator)).quantize(Decimal("1.0000000000"))

    def __str__(self) -> str:  # e.g., "2-for-1"
        return f"{self.numerator}-for-{self.denominator}"


class SecurityRef(BaseModel):
    ticker: Optional[str] = Field(None, description="Exchange ticker symbol")
    exchange_mic: Optional[str] = Field(None, description="MIC code for the listing exchange")
    isin: Optional[str] = None
    cusip: Optional[str] = None

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.upper()
        if not TICKER_RE.match(v):
            raise ValueError("ticker must be A–Z, 0–9, dot or hyphen, up to 12 chars")
        return v

    @field_validator("exchange_mic")
    @classmethod
    def _mic(cls, v: Optional[str]) -> Optional[str]:
        if v and not MIC_RE.match(v):
            raise ValueError("exchange_mic must be a valid MIC code")
        return v

    @field_validator("cusip")
    @classmethod
    def _cusip(cls, v: Optional[str]) -> Optional[str]:
        if v and not CUSIP_RE.match(v):
            raise ValueError("invalid CUSIP format")
        return v

    @field_validator("isin")
    @classmethod
    def _isin(cls, v: Optional[str]) -> Optional[str]:
        if v and not ISIN_RE.match(v):
            raise ValueError("invalid ISIN format")
        return v


class IssuerRef(BaseModel):
    name: Optional[str] = None
    cik: Optional[str] = Field(None, description="SEC 10-digit CIK with leading zeros")
    isin: Optional[str] = None  # Some issuers use an entity-level ISIN; optional
    country: Optional[str] = None  # ISO-3166 alpha-2 or alpha-3

    @field_validator("cik")
    @classmethod
    def _cik(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not CIK_RE.match(v):
            raise ValueError("CIK must be 10 digits, zero-padded")
        return v


# -----------------------
# Provenance
# -----------------------

class SourceInfo(BaseModel):
    source: str = Field(..., description="Short system name, e.g., sec_edgar, nikkei, nasdaq")
    doc_type: str = Field(..., description="Form or doc type, e.g., 8-K, press_release")
    source_url: str
    filing_date: Optional[date] = Field(None, description="Official filing/announcement date if known")
    retrieval_time: datetime = Field(default_factory=datetime.utcnow)
    content_sha256: Optional[str] = Field(None, description="SHA256 of the raw document bytes/text")
    reference_id: Optional[str] = Field(None, description="Internal pointer to your raw store")
    text_excerpt: Optional[str] = Field(None, description="Optional snippet around the extracted terms")


class FieldProvenance(BaseModel):
    field_name: str
    source_index: int = Field(..., description="Index into CorporateAction.sources[]")
    note: Optional[str] = Field(None, description="e.g., CSS selector, page number, or regex used")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


# -----------------------
# Consideration terms
# -----------------------

class ConsiderationLeg(BaseModel):
    type: str = Field(..., description="cash | stock | rights | other")
    cash_per_share: Optional[Money] = None
    stock_ratio: Optional[Ratio] = Field(
        None, description="New shares received per 1 old share if stock component applies"
    )
    stock_security: Optional[SecurityRef] = Field(
        None, description="Security received for stock consideration (e.g., acquirer's ticker)"
    )
    description: Optional[str] = Field(None, description="Free-form description for edge cases")

    @model_validator(mode="after")
    def _leg_semantics(self):
        if self.type == ConsiderationType.CASH and not self.cash_per_share:
            raise ValueError("cash leg requires cash_per_share")
        if self.type == ConsiderationType.STOCK and not self.stock_ratio:
            raise ValueError("stock leg requires stock_ratio")
        return self


class Terms(BaseModel):
    ratio: Optional[Ratio] = Field(
        None,
        description="Generic ratio used by splits/spin-offs/stock dividends (new per old).",
    )
    cash_per_share: Optional[Money] = Field(None, description="Generic cash per share (dividends, cash mergers)")
    consideration: Optional[List[ConsiderationLeg]] = Field(
        None, description="Detailed breakdown for mergers or mixed consideration"
    )


# -----------------------
# Main model
# -----------------------

class CorporateAction(BaseModel):
    # Identity
    event_id: Optional[str] = Field(
        None, description="Deterministic UUIDv5 if not provided"
    )

    action_type: str = Field(..., description="See ActionType enum")

    issuer: IssuerRef = Field(default_factory=IssuerRef)
    security: SecurityRef = Field(default_factory=SecurityRef)

    # Key dates
    announce_date: Optional[date] = None
    effective_date: Optional[date] = None
    ex_date: Optional[date] = None
    record_date: Optional[date] = None
    pay_date: Optional[date] = None

    # Terms
    terms: Terms = Field(default_factory=Terms)

    # Source & provenance
    sources: List[SourceInfo] = Field(default_factory=list)
    provenance: List[FieldProvenance] = Field(default_factory=list)

    # Quality & lifecycle
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    status: Optional[str] = Field(None, description="announced | amended | withdrawn | effective | cancelled")

    # Pipeline metadata
    extracted_fields_version: Optional[str] = None
    extraction_model: Optional[str] = None
    pipeline_version: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    supersedes_event_id: Optional[str] = Field(None, description="If this record supersedes a prior event")

    # Free-form notes
    notes: Optional[str] = None

    # Flexible extension bag for pipeline-specific metadata.
    # Example: {"extra_tickers": ["GOOG"], "all_tickers": ["GOOG","GOOGL"]}
    extras: Optional[Dict[str, Any]] = None

    # -------------------
    # Validators
    # -------------------

    @field_validator("action_type")
    @classmethod
    def _action_type(cls, v: str) -> str:
        allowed = {v for v in ActionType.__dict__.values() if isinstance(v, str)}
        if v not in allowed:
            raise ValueError(f"action_type must be one of: {sorted(allowed)}")
        return v

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, v: float) -> float:
        if v < 0 or v > 1:
            raise ValueError("confidence must be between 0 and 1")
        return float(v)

    @model_validator(mode="after")
    def _date_logic(self):
        # Soft logical checks (without business calendars)
        if self.announce_date and self.effective_date and self.effective_date < self.announce_date:
            raise ValueError("effective_date cannot be before announce_date")
        if self.record_date and self.pay_date and self.pay_date < self.record_date:
            raise ValueError("pay_date cannot be before record_date")
        # ex-date vs record_date: typically ex <= record_date; avoid strictness due to regional rules
        return self

    @model_validator(mode="after")
    def _terms_coherency(self):
        # Minimal semantic expectations by action_type
        t = self.terms
        if self.action_type in {ActionType.FORWARD_SPLIT, ActionType.REVERSE_SPLIT, ActionType.STOCK_DIVIDEND, ActionType.SPIN_OFF}:
            if not (t and (t.ratio or (t.consideration and any(leg.stock_ratio for leg in t.consideration)))):
                raise ValueError("split/stock-like actions require a ratio")
        if self.action_type in {ActionType.CASH_DIVIDEND, ActionType.MERGER_CASH, ActionType.MERGER_CASH_STOCK}:
            has_cash = bool(t and (t.cash_per_share or (t.consideration and any(leg.cash_per_share for leg in t.consideration))))
            if not has_cash:
                raise ValueError("cash-related actions require cash_per_share in terms or a cash consideration leg")
        if self.action_type in {ActionType.MERGER_STOCK, ActionType.MERGER_CASH_STOCK}:
            has_stock = bool(t and (t.ratio or (t.consideration and any(leg.stock_ratio for leg in t.consideration))))
            if not has_stock:
                raise ValueError("stock merger requires a stock ratio in terms or a stock consideration leg")
        return self

    @model_validator(mode="after")
    def _generate_event_id(self):
        if self.event_id:
            return self
        # Build a stable string from key fields
        parts: List[str] = []
        parts.append(self.action_type or "")
        # Issuer/security identifiers prioritized for stability
        if self.issuer.cik:
            parts.append(f"cik:{self.issuer.cik}")
        if self.security.isin:
            parts.append(f"isin:{self.security.isin}")
        if self.security.cusip:
            parts.append(f"cusip:{self.security.cusip}")
        if self.security.ticker:
            parts.append(f"ticker:{self.security.ticker}")
        # Dates (prefer effective/ex/record in that order for uniqueness)
        for dname in ("effective_date", "ex_date", "record_date", "announce_date"):
            dval = getattr(self, dname)
            if dval:
                parts.append(f"{dname}:{dval.isoformat()}")
        # Terms summary
        if self.terms.ratio:
            parts.append(f"ratio:{self.terms.ratio}")
        if self.terms.cash_per_share:
            parts.append(f"cash:{self.terms.cash_per_share.currency}:{self.terms.cash_per_share.amount}")
        if self.terms.consideration:
            for leg in self.terms.consideration:
                tag = f"leg:{leg.type}:{leg.cash_per_share.amount if leg.cash_per_share else ''}:{leg.stock_ratio if leg.stock_ratio else ''}:{leg.stock_security.ticker if leg.stock_security and leg.stock_security.ticker else ''}"
                parts.append(tag)
        # Hash
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        self.event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, digest))
        return self


# -----------------------
# Convenience factory for simple cases
# -----------------------

def simple_cash_dividend(
    ticker: str,
    exchange_mic: Optional[str],
    currency: str,
    cash_per_share: Union[str, Decimal, float],
    announce_date: Optional[date] = None,
    ex_date: Optional[date] = None,
    record_date: Optional[date] = None,
    pay_date: Optional[date] = None,
    source_url: Optional[str] = None,
    source: str = SourceSystem.SEC_EDGAR,
    doc_type: str = DocType.PRESS_RELEASE,
) -> CorporateAction:
    ca = CorporateAction(
        action_type=ActionType.CASH_DIVIDEND,
        issuer=IssuerRef(),
        security=SecurityRef(ticker=ticker, exchange_mic=exchange_mic),
        announce_date=announce_date,
        ex_date=ex_date,
        record_date=record_date,
        pay_date=pay_date,
        terms=Terms(cash_per_share=Money(currency=currency, amount=Decimal(str(cash_per_share)))),
        sources=[
            SourceInfo(
                source=source,
                doc_type=doc_type,
                source_url=source_url or "",
                filing_date=announce_date,
            )
        ],
    )
    return ca


# -----------------------
# Example usage (remove in production if desired)
# -----------------------
if __name__ == "__main__":
    # Forward split 2-for-1 example
    example = CorporateAction(
        action_type=ActionType.FORWARD_SPLIT,
        issuer=IssuerRef(cik="0000320193", name="Apple Inc."),
        security=SecurityRef(ticker="AAPL", exchange_mic="XNAS", isin="US0378331005"),
        announce_date=date(2020, 7, 30),
        effective_date=date(2020, 8, 31),
        ex_date=date(2020, 8, 31),
        record_date=date(2020, 8, 24),
        terms=Terms(ratio=Ratio(numerator=4, denominator=1)),
        sources=[
            SourceInfo(
                source=SourceSystem.SEC_EDGAR,
                doc_type=DocType.EIGHT_K,
                source_url="https://www.sec.gov/ix?doc=/Archives/edgar/data/0000320193/000032019320000096/a8-k20200730.htm",
                filing_date=date(2020, 7, 31),
            )
        ],
        confidence=0.98,
        extracted_fields_version="v1.0.0",
        extraction_model="gpt-5-structured-2025-07",
        pipeline_version="ca-pipeline-2025.08.01",
    )
    print(example.model_dump_json(indent=2))
