from __future__ import annotations

"""
Repository for persisting CorporateAction objects into Postgres (public schema).

Single responsibility: map Pydantic models to SQL and execute inserts/updates.
"""
from typing import List, Optional, Dict, Any
import json

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.core.db import get_engine
from src.models.corporate_action_model import (
    CorporateAction,
    SourceInfo,
    ConsiderationLeg,
    FieldProvenance,
)


def _details_json(ca: CorporateAction) -> str:
    """Serialize the full CorporateAction to JSON for details_json."""
    # Use Pydantic's JSON-compatible dump; default=str for Decimal/Date
    return json.dumps(ca.model_dump(mode="json"), default=str)


def _main_params(ca: CorporateAction) -> Dict[str, Any]:
    t = ca.terms
    ratio_num = t.ratio.numerator if (t and t.ratio) else None
    ratio_den = t.ratio.denominator if (t and t.ratio) else None
    cash_currency = t.cash_per_share.currency if (t and t.cash_per_share) else None
    cash_amount = t.cash_per_share.amount if (t and t.cash_per_share) else None

    return {
        "event_id": ca.event_id,
        "action_type": ca.action_type,
        "issuer_name": ca.issuer.name,
        "issuer_cik": ca.issuer.cik,
        # Store security-level identifiers in the main table
        "isin": ca.security.isin,
        "cusip": ca.security.cusip,
        "ticker": ca.security.ticker,
        "exchange_mic": ca.security.exchange_mic,
        # We currently do not track raw exchange name in the model; keep NULL
        "exchange_raw": None,
        "announce_date": ca.announce_date,
        "effective_date": ca.effective_date,
        "ex_date": ca.ex_date,
        "record_date": ca.record_date,
        "pay_date": ca.pay_date,
        "ratio_num": ratio_num,
        "ratio_den": ratio_den,
        "cash_currency": cash_currency,
        "cash_amount": cash_amount,
        "status": ca.status,
        "confidence": ca.confidence,
        "extracted_fields_version": ca.extracted_fields_version,
        "extraction_model": ca.extraction_model,
        "pipeline_version": ca.pipeline_version,
        "notes": ca.notes,
        "supersedes_event_id": ca.supersedes_event_id,
        "details_json": _details_json(ca),
    }


def _insert_or_update_corporate_action(engine: Engine, params: Dict[str, Any]) -> None:
    sql = text(
        """
        INSERT INTO public.corporate_actions (
            event_id, action_type, issuer_name, issuer_cik,
            isin, cusip, ticker, exchange_mic, exchange_raw,
            announce_date, effective_date, ex_date, record_date, pay_date,
            ratio_num, ratio_den, cash_currency, cash_amount,
            status, confidence,
            extracted_fields_version, extraction_model, pipeline_version, notes,
            supersedes_event_id, details_json
        ) VALUES (
            :event_id, :action_type, :issuer_name, :issuer_cik,
            :isin, :cusip, :ticker, :exchange_mic, :exchange_raw,
            :announce_date, :effective_date, :ex_date, :record_date, :pay_date,
            :ratio_num, :ratio_den, :cash_currency, :cash_amount,
            :status, :confidence,
            :extracted_fields_version, :extraction_model, :pipeline_version, :notes,
            :supersedes_event_id, CAST(:details_json AS JSONB)
        )
        ON CONFLICT (event_id) DO UPDATE SET
            action_type = EXCLUDED.action_type,
            issuer_name = EXCLUDED.issuer_name,
            issuer_cik = EXCLUDED.issuer_cik,
            isin = EXCLUDED.isin,
            cusip = EXCLUDED.cusip,
            ticker = EXCLUDED.ticker,
            exchange_mic = EXCLUDED.exchange_mic,
            exchange_raw = EXCLUDED.exchange_raw,
            announce_date = EXCLUDED.announce_date,
            effective_date = EXCLUDED.effective_date,
            ex_date = EXCLUDED.ex_date,
            record_date = EXCLUDED.record_date,
            pay_date = EXCLUDED.pay_date,
            ratio_num = EXCLUDED.ratio_num,
            ratio_den = EXCLUDED.ratio_den,
            cash_currency = EXCLUDED.cash_currency,
            cash_amount = EXCLUDED.cash_amount,
            status = EXCLUDED.status,
            confidence = EXCLUDED.confidence,
            extracted_fields_version = EXCLUDED.extracted_fields_version,
            extraction_model = EXCLUDED.extraction_model,
            pipeline_version = EXCLUDED.pipeline_version,
            notes = EXCLUDED.notes,
            supersedes_event_id = EXCLUDED.supersedes_event_id,
            details_json = EXCLUDED.details_json,
            updated_at = NOW()
        """
    )
    with engine.begin() as conn:
        conn.execute(sql, params)


def _replace_sources(engine: Engine, event_id: str, sources: List[SourceInfo]) -> None:
    # Merge/upsert semantics: preserve existing rows; upsert by unique key
    # (event_id, source, COALESCE(reference_id, source_url), COALESCE(doc_type,'')).
    ins_sql = text(
        """
        INSERT INTO public.corporate_action_sources (
            event_id, source, doc_type, source_url, filing_date,
            retrieval_time, reference_id, content_sha256, text_excerpt
        ) VALUES (
            :event_id, :source, :doc_type, :source_url, :filing_date,
            :retrieval_time, :reference_id, :content_sha256, :text_excerpt
        )
        ON CONFLICT (event_id, source, reference_id)
        DO UPDATE SET
            doc_type = EXCLUDED.doc_type,
            source_url = EXCLUDED.source_url,
            filing_date = EXCLUDED.filing_date,
            retrieval_time = EXCLUDED.retrieval_time,
            content_sha256 = EXCLUDED.content_sha256,
            text_excerpt = EXCLUDED.text_excerpt
        """
    )

    ins_url_sql = text(
        """
        INSERT INTO public.corporate_action_sources (
            event_id, source, doc_type, source_url, filing_date,
            retrieval_time, reference_id, content_sha256, text_excerpt
        ) VALUES (
            :event_id, :source, :doc_type, :source_url, :filing_date,
            :retrieval_time, :reference_id, :content_sha256, :text_excerpt
        )
        ON CONFLICT (event_id, source, source_url)
        DO UPDATE SET
            doc_type = EXCLUDED.doc_type,
            filing_date = EXCLUDED.filing_date,
            retrieval_time = EXCLUDED.retrieval_time,
            content_sha256 = EXCLUDED.content_sha256,
            text_excerpt = EXCLUDED.text_excerpt
        """
    )

    with engine.begin() as conn:
        for s in sources:
            params = {
                "event_id": event_id,
                "source": s.source,
                "doc_type": s.doc_type,
                "source_url": s.source_url,
                "filing_date": s.filing_date,
                "retrieval_time": s.retrieval_time,
                "reference_id": s.reference_id,
                "content_sha256": s.content_sha256,
                "text_excerpt": s.text_excerpt,
            }
            if s.reference_id:
                conn.execute(ins_sql, params)
            else:
                conn.execute(ins_url_sql, params)


def _replace_consideration_legs(engine: Engine, event_id: str, legs: Optional[List[ConsiderationLeg]]) -> None:
    if not legs:
        # Still clear any existing legs for idempotency
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM public.corporate_action_consideration_legs WHERE event_id = :event_id"), {"event_id": event_id})
        return

    del_sql = text("DELETE FROM public.corporate_action_consideration_legs WHERE event_id = :event_id")
    ins_sql = text(
        """
        INSERT INTO public.corporate_action_consideration_legs (
            event_id, type, cash_currency, cash_amount,
            stock_ratio_num, stock_ratio_den,
            stock_security_ticker, stock_security_exchange_mic
        ) VALUES (
            :event_id, :type, :cash_currency, :cash_amount,
            :stock_ratio_num, :stock_ratio_den,
            :stock_security_ticker, :stock_security_exchange_mic
        )
        """
    )
    with engine.begin() as conn:
        conn.execute(del_sql, {"event_id": event_id})
        for leg in legs:
            params = {
                "event_id": event_id,
                "type": leg.type,
                "cash_currency": (leg.cash_per_share.currency if leg.cash_per_share else None),
                "cash_amount": (leg.cash_per_share.amount if leg.cash_per_share else None),
                "stock_ratio_num": (leg.stock_ratio.numerator if leg.stock_ratio else None),
                "stock_ratio_den": (leg.stock_ratio.denominator if leg.stock_ratio else None),
                "stock_security_ticker": (leg.stock_security.ticker if leg.stock_security else None),
                "stock_security_exchange_mic": (leg.stock_security.exchange_mic if leg.stock_security else None),
            }
            conn.execute(ins_sql, params)


def _replace_provenance(engine: Engine, event_id: str, prov: Optional[List[FieldProvenance]]) -> None:
    if not prov:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM public.corporate_action_provenance WHERE event_id = :event_id"), {"event_id": event_id})
        return

    del_sql = text("DELETE FROM public.corporate_action_provenance WHERE event_id = :event_id")
    ins_sql = text(
        """
        INSERT INTO public.corporate_action_provenance (
            event_id, field_name, source_index, note, confidence
        ) VALUES (
            :event_id, :field_name, :source_index, :note, :confidence
        )
        """
    )
    with engine.begin() as conn:
        conn.execute(del_sql, {"event_id": event_id})
        for fp in prov:
            params = {
                "event_id": event_id,
                "field_name": fp.field_name,
                "source_index": fp.source_index,
                "note": fp.note,
                "confidence": fp.confidence,
            }
            conn.execute(ins_sql, params)


def persist_corporate_action(ca: CorporateAction, engine: Optional[Engine] = None) -> None:
    """Upsert a single CorporateAction and replace its child records.

    Args:
        ca: CorporateAction instance to persist.
        engine: Optional SQLAlchemy engine. If None, uses shared engine.
    """
    if ca.event_id is None:
        # Re-validate to trigger event_id generation if missing
        ca = CorporateAction(**ca.model_dump())

    eng = engine or get_engine()
    params = _main_params(ca)
    _insert_or_update_corporate_action(eng, params)
    _replace_sources(eng, ca.event_id, ca.sources)
    _replace_consideration_legs(eng, ca.event_id, ca.terms.consideration if ca.terms else None)
    _replace_provenance(eng, ca.event_id, ca.provenance)


def persist_corporate_actions(cas: List[CorporateAction], engine: Optional[Engine] = None) -> int:
    """Persist a list of CorporateActions.

    Returns the number of items processed.
    """
    if not cas:
        return 0
    eng = engine or get_engine()
    for ca in cas:
        persist_corporate_action(ca, engine=eng)
    return len(cas)
