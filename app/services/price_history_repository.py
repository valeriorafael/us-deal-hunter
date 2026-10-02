from datetime import datetime

from app.models.price_history import PriceHistory
from app.services.database import backup_database, connect


class PriceHistoryRepository:
    def __init__(self, db_path: str = "data/deal_hunter.db"):
        self.db_path = db_path

        self._connection = connect(self.db_path)

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
            ON CONFLICT (
                product_id,
                substr(recorded_at, 1, 10)
            )
            DO UPDATE SET
                price = excluded.price,
                currency = excluded.currency,
                recorded_at = excluded.recorded_at
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

    def count_older_than(self, cutoff: datetime) -> int:
        row = self._connection.execute(
            """
            SELECT COUNT(*)
            FROM price_history
            WHERE recorded_at < ?
            """,
            (cutoff.isoformat(),),
        ).fetchone()

        return row[0]

    def prune_older_than(self, cutoff: datetime) -> int:
        backup_database(self._connection, self.db_path)

        return self.delete_older_than(cutoff)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "PriceHistoryRepository":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
