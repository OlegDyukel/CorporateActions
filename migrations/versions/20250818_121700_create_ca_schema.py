"""
Create CA schema, tables, indexes, and triggers

Revision ID: c6a6b7e0f3a1
Revises: 
Create Date: 2025-08-18 12:17:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa  # noqa: F401  (import kept for Alembic typing and future use)

# revision identifiers, used by Alembic.
revision: str = "c6a6b7e0f3a1"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DDL_SQL = r"""

-- helper: auto-update updated_at on row update
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- main events table (one row per corporate action)
CREATE TABLE IF NOT EXISTS public.corporate_actions (
  event_id TEXT PRIMARY KEY,
  action_type TEXT NOT NULL,
  issuer_name TEXT,
  issuer_cik CHAR(10),
  isin CHAR(12),
  cusip CHAR(9),

  ticker TEXT,
  exchange_mic CHAR(4),
  exchange_raw TEXT,

  announce_date DATE,
  effective_date DATE,
  ex_date DATE,
  record_date DATE,
  pay_date DATE,

  ratio_num INT,
  ratio_den INT,
  cash_currency CHAR(3),
  cash_amount NUMERIC(18,6),

  status TEXT,
  confidence REAL,

  extracted_fields_version TEXT,
  extraction_model TEXT,
  pipeline_version TEXT,
  notes TEXT,

  supersedes_event_id TEXT NULL,
  details_json JSONB,

  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- keep updated_at fresh
DROP TRIGGER IF EXISTS trg_corporate_actions_updated_at ON public.corporate_actions;
CREATE TRIGGER trg_corporate_actions_updated_at
BEFORE UPDATE ON public.corporate_actions
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- sources (per-source audit trail)
CREATE TABLE IF NOT EXISTS public.corporate_action_sources (
  id BIGSERIAL PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES public.corporate_actions(event_id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  doc_type TEXT,
  source_url TEXT,
  filing_date DATE,
  retrieval_time TIMESTAMPTZ,
  reference_id TEXT,
  content_sha256 TEXT,
  text_excerpt TEXT
);

-- consideration legs (for mixed cash/stock)
CREATE TABLE IF NOT EXISTS public.corporate_action_consideration_legs (
  id BIGSERIAL PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES public.corporate_actions(event_id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  cash_currency CHAR(3),
  cash_amount NUMERIC(18,6),
  stock_ratio_num INT,
  stock_ratio_den INT,
  stock_security_ticker TEXT,
  stock_security_exchange_mic CHAR(4)
);

-- provenance (optional; per-field trace)
CREATE TABLE IF NOT EXISTS public.corporate_action_provenance (
  id BIGSERIAL PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES public.corporate_actions(event_id) ON DELETE CASCADE,
  field_name TEXT,
  source_index INT,
  note TEXT,
  confidence REAL
);

-- useful indexes
CREATE INDEX IF NOT EXISTS idx_ca_ticker_effdate    ON public.corporate_actions (ticker, effective_date);
CREATE INDEX IF NOT EXISTS idx_ca_action_effdate    ON public.corporate_actions (action_type, effective_date);
CREATE INDEX IF NOT EXISTS idx_ca_exchange          ON public.corporate_actions (exchange_mic);
CREATE INDEX IF NOT EXISTS idx_src_event_id         ON public.corporate_action_sources (event_id);
CREATE INDEX IF NOT EXISTS idx_legs_event_id        ON public.corporate_action_consideration_legs (event_id);

"""


def upgrade() -> None:
    op.execute(DDL_SQL)


def downgrade() -> None:
    op.execute(
        r"""
        BEGIN;
        DROP TABLE IF EXISTS public.corporate_action_provenance;
        DROP TABLE IF EXISTS public.corporate_action_consideration_legs;
        DROP TABLE IF EXISTS public.corporate_action_sources;
        DROP TRIGGER IF EXISTS trg_corporate_actions_updated_at ON public.corporate_actions;
        DROP TABLE IF EXISTS public.corporate_actions;
        DROP FUNCTION IF EXISTS public.set_updated_at();
        COMMIT;
        """
    )
