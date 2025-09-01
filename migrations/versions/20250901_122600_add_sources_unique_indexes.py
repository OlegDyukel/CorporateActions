"""
Add unique partial indexes for sources upsert

Revision ID: f8b5a8e0a123
Revises: c6a6b7e0f3a1
Create Date: 2025-09-01 12:26:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8b5a8e0a123"
down_revision: Union[str, None] = "c6a6b7e0f3a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_cas_event_source_refid
          ON public.corporate_action_sources (event_id, source, reference_id)
          WHERE reference_id IS NOT NULL;

        CREATE UNIQUE INDEX IF NOT EXISTS uq_cas_event_source_url
          ON public.corporate_action_sources (event_id, source, source_url)
          WHERE reference_id IS NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        r"""
        DROP INDEX IF EXISTS public.uq_cas_event_source_refid;
        DROP INDEX IF EXISTS public.uq_cas_event_source_url;
        """
    )
