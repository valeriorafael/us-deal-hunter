import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.publication.base import (
    DEFAULT_PUBLICATION_COOLDOWN,
    STATUS_PENDING,
    STATUS_PUBLISHED,
    STATUS_RECONCILIATION,
    STATUS_SENDING,
)
from app.services.database import connect

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AttemptRecord:
    """A stored attempt that may still be recoverable (phase 4)."""

    attempt_id: int
    product_id: str
    affiliate_url: str
    published_at: datetime
    message_id: int


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
        status: str = STATUS_PUBLISHED,
        *,
        message_id: int | None = None,
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
                status,
                message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                message_id,
            ),
        )

        self._connection.commit()

    def begin_attempt(
        self,
        *,
        product_id: str,
        affiliate_url: str,
        price: float,
        attempted_at: datetime,
        title: str | None = None,
        score: float | None = None,
        label: str | None = None,
        discount_vs_30d: float | None = None,
        source_query: str | None = None,
    ) -> int:
        """T1: record the intent to publish (fail-closed).

        A publication must never be sent without a committed
        PENDING row, so the insert is committed immediately and
        its id identifies the attempt for the rest of the flow.
        """
        cursor = self._connection.execute(
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
                status,
                message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                product_id,
                affiliate_url,
                price,
                attempted_at.isoformat(),
                title,
                score,
                label,
                discount_vs_30d,
                source_query,
                STATUS_PENDING,
            ),
        )

        self._connection.commit()

        return int(cursor.lastrowid)

    def begin_attempt_exclusive(
        self,
        *,
        duplicate_check: Callable[[], bool],
        **fields,
    ) -> int | None:
        """T1 under BEGIN IMMEDIATE (H1).

        The duplicate check and the PENDING insert run inside one
        write transaction, so two concurrent runs can never both
        decide that a product is free and both send a message.
        Returns None when the check says the product must not be
        published again.
        """
        try:
            if self._connection.in_transaction:
                # a statement failed before committing and left an
                # empty transaction behind; drop it so BEGIN works
                self._connection.rollback()

            self._connection.execute("BEGIN IMMEDIATE")

            if duplicate_check():
                self._connection.rollback()

                return None

            return self.begin_attempt(**fields)
        except BaseException:
            if self._connection.in_transaction:
                self._connection.rollback()

            raise

    def has_inflight_attempt(self, product_id: str) -> bool:
        """True while an attempt for this product may still run.

        PENDING and SENDING rows belong either to this run or to
        a crashed one; publishing again now would duplicate.
        """
        row = self._connection.execute(
            """
            SELECT 1
            FROM publications
            WHERE product_id = ?
              AND status IN (?, ?)
            LIMIT 1
            """,
            (product_id, STATUS_PENDING, STATUS_SENDING),
        ).fetchone()

        return row is not None

    def _set_status(
        self,
        attempt_id: int,
        status: str,
    ) -> None:
        self._connection.execute(
            """
            UPDATE publications
            SET status = ?
            WHERE id = ?
            """,
            (status, attempt_id),
        )

        self._connection.commit()

    def mark_sending(self, attempt_id: int) -> None:
        """T2: committed right before invoking the publisher."""
        self._set_status(attempt_id, STATUS_SENDING)

    def mark_published(
        self,
        attempt_id: int,
        published_at: datetime,
        message_id: int | None = None,
    ) -> None:
        """T3: the publisher confirmed delivery.

        The handle is committed first (T3a) and the state change
        second (T3b), so a crash between the two can never lose
        the only reference to a message already in the channel.
        """
        self._store_message_id(attempt_id, message_id)
        self._apply_published_state(attempt_id, published_at)

    def _store_message_id(
        self,
        attempt_id: int,
        message_id: int | None,
    ) -> None:
        """T3a: persist the delivery handle on its own."""
        self._connection.execute(
            """
            UPDATE publications
            SET message_id = ?
            WHERE id = ?
            """,
            (message_id, attempt_id),
        )

        self._connection.commit()

    def _apply_published_state(
        self,
        attempt_id: int,
        published_at: datetime,
    ) -> None:
        """T3b: flip the row to PUBLISHED."""
        self._connection.execute(
            """
            UPDATE publications
            SET
                status = ?,
                published_at = ?
            WHERE id = ?
            """,
            (
                STATUS_PUBLISHED,
                published_at.isoformat(),
                attempt_id,
            ),
        )

        self._connection.commit()

    def drop_attempt(self, attempt_id: int) -> None:
        """T4: outcome known and nothing was published."""
        self._connection.execute(
            "DELETE FROM publications WHERE id = ?",
            (attempt_id,),
        )

        self._connection.commit()

    def mark_unknown(self, attempt_id: int) -> None:
        """T5/T6: outcome unknown, keep as history."""
        self._set_status(attempt_id, STATUS_RECONCILIATION)

    def reconcile_stale_attempts(
        self,
        older_than: datetime,
    ) -> int:
        """Resolve orphaned attempts left by a crash (T7).

        Only rows older than the limit are touched so a run that
        is still in progress is never disturbed. Each resolved
        row is logged with its previous status (spec 4.5).
        """
        stale = self._connection.execute(
            """
            SELECT id, status
            FROM publications
            WHERE status IN (?, ?)
              AND published_at < ?
            """,
            (
                STATUS_PENDING,
                STATUS_SENDING,
                older_than.isoformat(),
            ),
        ).fetchall()

        self._connection.execute(
            """
            UPDATE publications
            SET status = ?
            WHERE status IN (?, ?)
              AND published_at < ?
            """,
            (
                STATUS_RECONCILIATION,
                STATUS_PENDING,
                STATUS_SENDING,
                older_than.isoformat(),
            ),
        )

        self._connection.commit()

        for attempt_id, previous_status in stale:
            logger.warning(
                "stale publication attempt %s reconciled "
                "(previous status=%s)",
                attempt_id,
                previous_status,
            )

        return len(stale)

    def attempts_for_verification(
        self,
        *,
        stale_before: datetime,
        not_older_than: datetime,
        limit: int,
    ) -> list[AttemptRecord]:
        """Stored attempts that can be probed in the channel.

        Only SENDING/RECONCILIATION rows carrying a message id
        are candidates: without the id nothing can be verified,
        rows younger than ``stale_before`` may still belong to a
        run that is active, and rows older than
        ``not_older_than`` are outside the verification window.
        """
        rows = self._connection.execute(
            """
            SELECT
                id,
                product_id,
                affiliate_url,
                published_at,
                message_id
            FROM publications
            WHERE status IN (?, ?)
              AND message_id IS NOT NULL
              AND published_at < ?
              AND published_at >= ?
            ORDER BY published_at ASC
            LIMIT ?
            """,
            (
                STATUS_SENDING,
                STATUS_RECONCILIATION,
                stale_before.isoformat(),
                not_older_than.isoformat(),
                limit,
            ),
        ).fetchall()

        return [
            AttemptRecord(
                attempt_id=row[0],
                product_id=row[1],
                affiliate_url=row[2],
                published_at=datetime.fromisoformat(row[3]),
                message_id=row[4],
            )
            for row in rows
        ]

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