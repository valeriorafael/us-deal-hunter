import sqlite3
from datetime import datetime

from app.models.price_history import PriceHistory


class PriceHistoryRepository:
    def __init__(self, db_path: str = "data/deal_hunter.db"):
        self.db_path = db_path

        self._connection = sqlite3.connect(self.db_path)

        self._create_table()

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
