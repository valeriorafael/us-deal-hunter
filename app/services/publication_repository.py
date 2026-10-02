from datetime import datetime, timedelta

from app.publication.base import DEFAULT_PUBLICATION_COOLDOWN
from app.services.database import connect


class PublicationRepository:
    def __init__(
        self,
        db_path: str = "data/deal_hunter.db",
    ):
        self.db_path = db_path

        self._connection = connect(self.db_path)

    def record(
        self,
        product_id: str,
        affiliate_url: str,
        price: float,
        published_at: datetime,
        title: str | None = None,
        score: float | None = None,
        label: str | None = None,
        discount_vs_30d: float | None = None,
        source_query: str | None = None,
        status: str = "PUBLISHED",
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO publications (
                product_id,
                affiliate_url,
                price,
                published_at,
                title,
                score,
                label,
                discount_vs_30d,
                source_query,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                affiliate_url,
                price,
                published_at.isoformat(),
                title,
                score,
                label,
                discount_vs_30d,
                source_query,
                status,
            ),
        )

        self._connection.commit()

    def was_published_recently(
        self,
        product_id: str,
        now: datetime | None = None,
        cooldown: timedelta = DEFAULT_PUBLICATION_COOLDOWN,
    ) -> bool:
        now = now or datetime.now()

        row = self._connection.execute(
            """
            SELECT published_at
            FROM publications
            WHERE product_id = ?
              AND status = 'PUBLISHED'
            ORDER BY published_at DESC
            LIMIT 1
            """,
            (product_id,),
        ).fetchone()

        if row is None:
            return False

        published_at = datetime.fromisoformat(row[0])

        return published_at > now - cooldown

    def was_published(self, product_id: str) -> bool:
        row = self._connection.execute(
            """
            SELECT 1
            FROM publications
            WHERE product_id = ?
              AND status = 'PUBLISHED'
            LIMIT 1
            """,
            (product_id,),
        ).fetchone()

        return row is not None

    def count(self, product_id: str) -> int:
        row = self._connection.execute(
            """
            SELECT COUNT(*)
            FROM publications
            WHERE product_id = ?
            """,
            (product_id,),
        ).fetchone()

        return row[0]

    def total(self) -> int:
        row = self._connection.execute(
            """
            SELECT COUNT(*)
            FROM publications
            WHERE status = 'PUBLISHED'
            """
        ).fetchone()

        return row[0]

    def count_since(
        self,
        since: datetime,
    ) -> int:
        row = self._connection.execute(
            """
            SELECT COUNT(*)
            FROM publications
            WHERE status = 'PUBLISHED'
              AND published_at >= ?
            """,
            (since.isoformat(),),
        ).fetchone()

        return row[0]

    def average_score(self) -> float | None:
        row = self._connection.execute(
            """
            SELECT AVG(score)
            FROM publications
            WHERE status = 'PUBLISHED'
              AND score IS NOT NULL
            """
        ).fetchone()

        return row[0]

    def top_queries(
        self,
        limit: int = 10,
    ) -> list[tuple[str, int]]:
        rows = self._connection.execute(
            """
            SELECT
                source_query,
                COUNT(*) AS publication_count
            FROM publications
            WHERE status = 'PUBLISHED'
              AND source_query IS NOT NULL
            GROUP BY source_query
            ORDER BY publication_count DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [
            (row[0], row[1])
            for row in rows
        ]

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "PublicationRepository":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()