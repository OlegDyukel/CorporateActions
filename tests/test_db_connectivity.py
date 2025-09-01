import unittest
from typing import Set, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.core.db import get_engine


class DBConnectivityConsistencyTests(unittest.TestCase):
    """Tests database connectivity and basic schema consistency.

    Skips the suite if DATABASE_URL is not configured or the DB is unreachable.
    """

    engine: Optional[Engine] = None

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.engine = get_engine()
            # Validate a simple connection and statement execution
            with cls.engine.connect() as conn:
                conn.execute(text("select 1"))
        except Exception as e:  # pragma: no cover - environment dependent
            raise unittest.SkipTest(f"Skipping DB tests: {e}")

    @classmethod
    def tearDownClass(cls) -> None:
        # Ensure pooled connections are released
        if cls.engine is not None:
            try:
                cls.engine.dispose()
            finally:
                cls.engine = None

    def test_select_1_connectivity(self) -> None:
        """Ensure the database is reachable and a simple query works."""
        assert self.engine is not None
        with self.engine.connect() as conn:
            ok = conn.execute(text("select 1 as ok")).scalar()
        self.assertEqual(ok, 1)

    def test_schema_consistency(self) -> None:
        """Check required tables and key columns exist in the public schema."""
        assert self.engine is not None
        required_tables: Set[str] = {
            "corporate_actions",
            "corporate_action_sources",
            "corporate_action_consideration_legs",
            "corporate_action_provenance",
        }
        with self.engine.connect() as conn:
            rs = conn.execute(text(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                """
            ))
            tables = {row[0] for row in rs.fetchall()}
        missing = required_tables - tables
        self.assertFalse(
            missing,
            f"Missing expected tables in public schema: {sorted(missing)}"
        )

        required_columns: Set[str] = {"event_id", "action_type", "issuer_name", "details_json", "updated_at"}
        with self.engine.connect() as conn:
            rs = conn.execute(text(
                """
                select column_name
                from information_schema.columns
                where table_schema = 'public' and table_name = 'corporate_actions'
                """
            ))
            cols = {row[0] for row in rs.fetchall()}
        missing_cols = required_columns - cols
        self.assertFalse(
            missing_cols,
            f"Missing columns in public.corporate_actions: {sorted(missing_cols)}"
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
