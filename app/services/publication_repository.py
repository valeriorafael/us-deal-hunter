import sqlite3
from datetime import datetime, timedelta


class PublicationRepository:
    def __init__(
        self,
        db_path: str = "data/deal_hunter.db",
    ):
        self.db_path = db_path

        self._connection = sqlite3.connect(
            self.db_path
        )

        self._create_table()
        self._migrate_table()

    def _create_table(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS publications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                affiliate_url TEXT NOT NULL,
                price REAL NOT NULL,
                published_at TEXT NOT NULL,
                title TEXT,
                score REAL,
                label TEXT,
                discount_vs_30d REAL,
                source_query TEXT,
                status TEXT NOT NULL DEFAULT 'PUBLISHED'
            )
            """
        )

        self._connection.commit()

    def _migrate_table(self) -> None:
        columns = {
            row[1]
            for row in self._connection.execute(
                "PRAGMA table_info(publications)"
            ).fetchall()
        }

        migrations = {
            "title": "ALTER TABLE publications ADD COLUMN title TEXT",
            "score": "ALTER TABLE publications ADD COLUMN score REAL",
            "label": "ALTER TABLE publications ADD COLUMN label TEXT",
            "discount_vs_30d": (
                "ALTER TABLE publications "
                "ADD COLUMN discount_vs_30d REAL"
            ),
            "source_query": (
                "ALTER TABLE publications "
                "ADD COLUMN source_query TEXT"
            ),
            "status": (
                "ALTER TABLE publications "
                "ADD COLUMN status TEXT NOT NULL DEFAULT 'PUBLISHED'"
            ),
        }

        for column, statement in migrations.items():
            if column not in columns:
                self._connection.execute(statement)

        self._connection.commit()

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
        cooldown: timedelta = timedelta(hours=24),
    ) -> bool:
        now = now or datetime.now()

        row = self._connection.execute(
            """
            SELECT published_at
            FROM publications
            WHERE product_id = ?
            ORDER BY published_at DESC
            LIMIT 1
            """,
            (product_id,),
        ).fetchone()

        if row is None:
            return False

        published_at = datetime.fromisoformat(row[0])

        return published_at >= now - cooldown

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