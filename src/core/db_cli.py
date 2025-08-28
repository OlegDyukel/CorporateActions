from __future__ import annotations

"""
Simple DB CLI for inspection and ad-hoc read-only queries.

Usage examples (from project root):

  python -m src.core.db_cli list-schemas
  python -m src.core.db_cli list-tables --schema public
  python -m src.core.db_cli alembic-version
  python -m src.core.db_cli query --sql "select count(*) from public.corporate_actions"

This module's single responsibility is to expose a small CLI over the shared DB engine.
"""

from dataclasses import dataclass
from typing import Iterable, List, Optional
import argparse

from sqlalchemy import text
from sqlalchemy.engine import Engine, Row

from src.core.db import get_engine


@dataclass(frozen=True)
class QueryResult:
    columns: List[str]
    rows: List[List[object]]


def _fetch_all(engine: Engine, sql: str) -> QueryResult:
    with engine.connect() as conn:
        rs = conn.execute(text(sql))
        cols = list(rs.keys())
        data = [list(row) for row in rs.fetchall()]
        return QueryResult(columns=cols, rows=data)


def _print_table(result: QueryResult) -> None:
    if not result.columns:
        print("(no columns)")
        return
    # Simple tab-separated output
    print("\t".join(result.columns))
    for row in result.rows:
        print("\t".join("" if v is None else str(v) for v in row))


def list_schemas(engine: Engine) -> None:
    sql = """
    select schema_name
    from information_schema.schemata
    order by 1
    """
    res = _fetch_all(engine, sql)
    _print_table(res)


def list_tables(engine: Engine, schema: str) -> None:
    sql = """
    select table_schema, table_name
    from information_schema.tables
    where table_schema = :schema
    order by table_name
    """
    with engine.connect() as conn:
        rs = conn.execute(text(sql), {"schema": schema})
        cols = list(rs.keys())
        data = [list(row) for row in rs.fetchall()]
    _print_table(QueryResult(columns=cols, rows=data))


def alembic_version(engine: Engine) -> None:
    sql = "select version_num from public.alembic_version"
    try:
        res = _fetch_all(engine, sql)
    except Exception as e:
        print(f"Error reading alembic version: {e}")
        return
    _print_table(res)


def ad_hoc_query(engine: Engine, sql: str) -> None:
    res = _fetch_all(engine, sql)
    _print_table(res)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="DB inspection CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-schemas", help="List all schemas")

    p_tables = sub.add_parser("list-tables", help="List tables in a schema")
    p_tables.add_argument("--schema", default="public", help="Schema name (default: public)")

    sub.add_parser("alembic-version", help="Show alembic version in public schema")

    p_query = sub.add_parser("query", help="Run an ad-hoc read-only SQL query")
    p_query.add_argument("--sql", required=True, help="SQL to execute")

    return p


def main(argv: Optional[List[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    engine = get_engine()

    if args.cmd == "list-schemas":
        list_schemas(engine)
    elif args.cmd == "list-tables":
        list_tables(engine, args.schema)
    elif args.cmd == "alembic-version":
        alembic_version(engine)
    elif args.cmd == "query":
        ad_hoc_query(engine, args.sql)
    else:  # pragma: no cover - argparse enforces choices
        parser.error(f"Unknown command: {args.cmd}")


if __name__ == "__main__":  # pragma: no cover
    main()
