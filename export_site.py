#!/usr/bin/env python3
"""SQLite -> site/deals.json (spec 18.1, Fase 5 / M1).

Reads the existing database strictly read-only (``mode=ro``) and
writes the public document through :mod:`app.services.site_export`.

The exporter never migrates, never writes back to the database
and projects a single channel: ``channel`` exists since the schema
migration 5 and only ``WEBSITE`` publications reach the site.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.publication.base import (
    CHANNEL_WEBSITE,
    STATUS_PUBLISHED,
)
from app.services.site_export import (
    SiteHistoryPoint,
    SitePublication,
    build_document,
    write_document_atomic,
)

DEFAULT_DB = "data/deal_hunter.db"
DEFAULT_OUTPUT = "site/deals.json"

PUBLICATIONS_SQL = """
SELECT
    product_id,
    title,
    price,
    published_at,
    affiliate_url,
    score,
    label,
    discount_vs_30d,
    source_query
FROM publications
WHERE status = ? AND channel = ?
ORDER BY published_at DESC, id DESC
"""

HISTORY_SQL = """
SELECT price, recorded_at
FROM price_history
WHERE product_id = ?
ORDER BY recorded_at ASC
"""


def open_read_only(db_path: str | Path) -> sqlite3.Connection:
    """Open an existing database without any write access."""
    path = Path(db_path)

    if not path.is_file():
        raise FileNotFoundError(
            f"database not found: {db_path}"
        )

    uri = f"file:{path.resolve().as_posix()}?mode=ro"

    return sqlite3.connect(uri, uri=True)


def load_publications(
    connection: sqlite3.Connection,
) -> list[SitePublication]:
    """PUBLISHED rows of the WEBSITE channel only (spec 18.1)."""
    rows = connection.execute(
        PUBLICATIONS_SQL,
        (STATUS_PUBLISHED, CHANNEL_WEBSITE),
    ).fetchall()

    return [
        SitePublication(
            product_id=row[0],
            title=row[1],
            price=row[2],
            published_at=datetime.fromisoformat(row[3]),
            affiliate_url=row[4],
            score=row[5],
            label=row[6],
            discount_vs_30d=row[7],
            source_query=row[8],
        )
        for row in rows
    ]


def load_history(
    connection: sqlite3.Connection,
    product_id: str,
) -> list[SiteHistoryPoint]:
    rows = connection.execute(
        HISTORY_SQL,
        (product_id,),
    ).fetchall()

    return [
        SiteHistoryPoint(
            price=row[0],
            recorded_at=datetime.fromisoformat(row[1]),
        )
        for row in rows
    ]


def export(
    db_path: str | Path,
    output_path: str | Path,
    *,
    now: datetime | None = None,
) -> int:
    """Build and write the document; returns the deal count."""
    generated_at = now or datetime.now(timezone.utc)

    connection = open_read_only(db_path)

    try:
        publications = load_publications(connection)

        histories = {
            product_id: load_history(
                connection,
                product_id,
            )
            for product_id in {
                item.product_id for item in publications
            }
        }
    finally:
        connection.close()

    document = build_document(
        publications,
        histories,
        generated_at=generated_at,
    )

    write_document_atomic(output_path, document)

    return len(document["deals"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export PUBLISHED publications into the public "
            "site/deals.json document."
        )
    )

    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help=f"SQLite database (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUTPUT,
        help=(
            f"output JSON file (default: {DEFAULT_OUTPUT})"
        ),
    )

    args = parser.parse_args(argv)

    try:
        count = export(args.db, args.out)
    except (
        FileNotFoundError,
        OSError,
        sqlite3.Error,
        ValueError,
    ) as exc:
        print(f"export failed: {exc}", file=sys.stderr)

        return 1

    print(f"Exported {count} deals to {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
