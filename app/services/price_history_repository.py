import sqlite3
from datetime import datetime

from app.models.price_history import PriceHistory


class PriceHistoryRepository:
    def __init__(self, db_path: str = "data/deal_hunter.db"):
        self.db_path = db_path

        self._connection = sqlite3.connect(self.db_path)

        self._create_table()
        self._create_index()

    def _create_table(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                price REAL NOT NULL,
                currency TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
            """
        )

        self._connection.commit()

    def _create_index(self) -> None:
        self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_price_history_product_recorded
            ON price_history (product_id, recorded_at)
            """
        )

        self._connection.commit()

    def save(self, item: PriceHistory) -> None:
        self._connection.execute(
            """
            INSERT INTO price_history (
                product_id,
                price,
                currency,
                recorded_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                item.product_id,
                item.price,
                item.currency,
                item.recorded_at.isoformat(),
            ),
        )

        self._connection.commit()

    def get_by_product(self, product_id: str) -> list[PriceHistory]:
        rows = self._connection.execute(
            """
            SELECT
                product_id,
                price,
                currency,
                recorded_at
            FROM price_history
            WHERE product_id = ?
            ORDER BY recorded_at ASC
            """,
            (product_id,),
        ).fetchall()

        return [
            PriceHistory(
                product_id=row[0],
                price=row[1],
                currency=row[2],
                recorded_at=datetime.fromisoformat(row[3]),
            )
            for row in rows
        ]

    def count(self, product_id: str) -> int:
        row = self._connection.execute(
            """
            SELECT COUNT(*)
            FROM price_history
            WHERE product_id = ?
            """,
            (product_id,),
        ).fetchone()

        return row[0]

    def delete_older_than(self, cutoff: datetime) -> int:
        # recorded_at is stored as an ISO 8601 string, so the
        # comparison is chronological as long as every stored
        # value uses the same format as the cutoff.
        cursor = self._connection.execute(
            """
            DELETE FROM price_history
            WHERE recorded_at < ?
            """,
            (cutoff.isoformat(),),
        )

        self._connection.commit()

        return cursor.rowcount
