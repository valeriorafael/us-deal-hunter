"""Phase 5 - Fases C and D: state machine + crash consistency.

Every transition of the PENDING/SENDING/PUBLISHED/RECONCILIATION
machine is exercised, including simulated crashes at each point
between "intent committed" and "publication persisted".
"""

import sqlite3
from datetime import datetime, timedelta

import pytest

from app.publication.base import PublicationResult, Verdict
from app.publication.service import PublicationService
from app.services.publication_repository import (
    PublicationRepository,
)

NOW = datetime(2026, 8, 15, 12, 0)
STALE = NOW - timedelta(seconds=601)
VERY_OLD = NOW - timedelta(days=49)

ALLOWED_STATES = {
    "PENDING",
    "SENDING",
    "PUBLISHED",
    "RECONCILIATION",
}


class CountingPublisher:
    def __init__(self, message_id=9):
        self.message_id = message_id
        self.calls = []

    def publish(self, deal):
        self.calls.append(deal.product.product_id)

        return PublicationResult(
            success=True,
            status="PUBLISHED",
            reason="Published.",
            message_id=self.message_id,
        )


class VerdictVerifier:
    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = []

    def verify_message(self, message_id, *, affiliate_url):
        self.calls.append(message_id)
        return self.verdict


def build_deal(product_id="123"):
    from app.models.deal import Deal
    from app.models.product import Product

    return Deal(
        product=Product(
            product_id=product_id,
            title="Test Product",
            current_price=75.0,
            average_price_30d=100.0,
            platform="amazon",
            affiliate_url=(
                f"https://www.amazon.com/dp/{product_id}"
                "?tag=test-20"
            ),
        ),
        score=88.0,
        label="GREAT",
        confidence="HIGH",
    )


def rows(db_path, product_id="123"):
    connection = sqlite3.connect(db_path)

    try:
        return connection.execute(
            "SELECT status, published_at, message_id "
            "FROM publications WHERE product_id = ? ORDER BY id",
            (product_id,),
        ).fetchall()
    finally:
        connection.close()


def statuses(db_path):
    connection = sqlite3.connect(db_path)

    try:
        return [
            row[0]
            for row in connection.execute(
                "SELECT status FROM publications ORDER BY id"
            ).fetchall()
        ]
    finally:
        connection.close()


def seed(
    db_path,
    *,
    status,
    published_at=STALE,
    message_id=None,
    product_id="123",
):
    repository = PublicationRepository(db_path)
    repository.record(
        product_id=product_id,
        affiliate_url="https://example.com",
        price=75.0,
        published_at=published_at,
        status=status,
        message_id=message_id,
    )
    repository.close()


class FailingConnection:
    """Delegating proxy that fails chosen statements once."""

    def __init__(self, real, fail_when):
        self._real = real
        self._fail_when = fail_when

    def execute(self, sql, *args):
        if self._fail_when(sql):
            raise sqlite3.OperationalError(
                "disk I/O error"
            )

        return self._real.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._real, name)


# ---------------------------------------------------------------------------
# Fase C - state machine
# ---------------------------------------------------------------------------


def test_schema_rejects_rows_without_timestamp(tmp_path):
    db_path = str(tmp_path / "publication.db")
    repository = PublicationRepository(db_path)
    repository.close()

    connection = sqlite3.connect(db_path)

    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO publications ("
                "product_id, affiliate_url, price, "
                "published_at, status"
                ") VALUES ('123', 'x', 1.0, NULL, 'PENDING')"
            )
    finally:
        connection.close()


def test_every_repository_transition_stays_in_the_vocabulary(
    tmp_path,
):
    db_path = str(tmp_path / "publication.db")
    repository = PublicationRepository(db_path)

    attempt_id = repository.begin_attempt(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        attempted_at=NOW,
    )

    assert statuses(db_path) == ["PENDING"]

    repository.mark_sending(attempt_id)
    assert statuses(db_path) == ["SENDING"]

    repository.mark_published(attempt_id, NOW, message_id=5)
    assert statuses(db_path) == ["PUBLISHED"]

    repository.mark_unknown(attempt_id)
    assert statuses(db_path) == ["RECONCILIATION"]

    assert set(statuses(db_path)) <= ALLOWED_STATES
    repository.close()


def test_reconcile_never_touches_terminal_or_foreign_states(
    tmp_path,
):
    db_path = str(tmp_path / "publication.db")
    seed(db_path, status="PUBLISHED", message_id=1)
    seed(db_path, status="RECONCILIATION", message_id=2)
    seed(db_path, status="SENDING", published_at=VERY_OLD)
    seed(db_path, status="PENDING", published_at=VERY_OLD)

    repository = PublicationRepository(db_path)
    service = PublicationService(
        publisher=CountingPublisher(),
        repository=repository,
    )
    first = service.reconcile_stale_attempts(now=NOW)
    second = service.reconcile_stale_attempts(now=NOW)

    assert first == 2
    assert second == 0
    assert statuses(db_path) == [
        "PUBLISHED",
        "RECONCILIATION",
        "RECONCILIATION",
        "RECONCILIATION",
    ]
    repository.close()


def test_verification_only_considers_sending_and_reconciliation(
    tmp_path,
):
    db_path = str(tmp_path / "publication.db")
    seed(db_path, status="PUBLISHED", message_id=1)
    seed(db_path, status="PENDING", message_id=2)
    seed(db_path, status="SENDING", message_id=None)
    seed(db_path, status="RECONCILIATION", message_id=None)

    repository = PublicationRepository(db_path)
    records = repository.attempts_for_verification(
        stale_before=STALE,
        not_older_than=NOW - timedelta(hours=48),
        limit=10,
    )

    assert records == []
    repository.close()


def test_reconciliation_without_message_id_never_becomes_a_candidate(
    tmp_path,
):
    """History row: never probed, never reconciled, never a
    cooldown blocker - stable across repeated runs (no eternal
    state flip, no crash)."""
    db_path = str(tmp_path / "publication.db")
    seed(db_path, status="RECONCILIATION", message_id=None)

    repository = PublicationRepository(db_path)
    verifier = VerdictVerifier(Verdict.EXISTS)
    service = PublicationService(
        publisher=CountingPublisher(),
        repository=repository,
        verifier=verifier,
    )

    for _ in range(3):
        assert service.verify_channel_attempts(now=NOW) == 0
        assert service.reconcile_stale_attempts(now=NOW) == 0

    assert verifier.calls == []
    assert statuses(db_path) == ["RECONCILIATION"]
    repository.close()


# ---------------------------------------------------------------------------
# Fase D - crash consistency, point by point
# ---------------------------------------------------------------------------


def test_crash_after_intent_commit_is_reconciled_and_retried(
    tmp_path,
):
    """Crash after T1 commit: row stays PENDING. Next run
    reconciles it and the product may be published again."""
    db_path = str(tmp_path / "publication.db")
    repository = PublicationRepository(db_path)
    repository.begin_attempt(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        attempted_at=STALE,
    )
    repository.close()

    service = PublicationService(
        publisher=CountingPublisher(),
        repository=PublicationRepository(db_path),
    )
    reconciled = service.reconcile_stale_attempts(now=NOW)
    assert reconciled == 1
    assert statuses(db_path) == ["RECONCILIATION"]

    publisher = CountingPublisher(message_id=4)
    outcome = PublicationService(
        publisher=publisher,
        repository=PublicationRepository(db_path),
    ).publish(build_deal(), now=NOW)

    assert outcome.success is True
    assert publisher.calls == ["123"]
    assert statuses(db_path) == [
        "RECONCILIATION",
        "PUBLISHED",
    ]


def test_crash_before_telegram_is_at_least_once(tmp_path):
    """Crash after mark_sending, before/while calling Telegram:
    SENDING without message id. The next run cannot probe it, so
    it reconciles and may send again (spec 16 at-least-once)."""
    db_path = str(tmp_path / "publication.db")
    seed(db_path, status="SENDING", published_at=STALE)

    publisher = CountingPublisher()
    service = PublicationService(
        publisher=publisher,
        repository=PublicationRepository(db_path),
        verifier=VerdictVerifier(Verdict.EXISTS),
    )

    assert service.verify_channel_attempts(now=NOW) == 0
    assert service.reconcile_stale_attempts(now=NOW) == 1

    outcome = service.publish(build_deal(), now=NOW)

    assert outcome.success is True
    assert publisher.calls == ["123"]


def test_crash_between_message_id_and_state_recovers_via_verify(
    tmp_path,
):
    """Crash after T3a: SENDING + message_id. Next run verifies
    the channel and restores PUBLISHED with the original send
    time, so the cooldown still blocks a duplicate."""
    db_path = str(tmp_path / "publication.db")
    seed(db_path, status="SENDING", published_at=STALE, message_id=42)

    verifier = VerdictVerifier(Verdict.EXISTS)
    service = PublicationService(
        publisher=CountingPublisher(),
        repository=PublicationRepository(db_path),
        verifier=verifier,
    )
    verified = service.verify_channel_attempts(now=NOW)

    assert verified == 1
    assert verifier.calls == [42]
    assert rows(db_path) == [
        ("PUBLISHED", STALE.isoformat(), 42)
    ]

    publisher = CountingPublisher()
    outcome = PublicationService(
        publisher=publisher,
        repository=PublicationRepository(db_path),
    ).publish(build_deal(), now=NOW)

    assert outcome.status == "DUPLICATE_PUBLICATION"
    assert publisher.calls == []


def test_crash_after_send_channel_says_absent_then_retry(
    tmp_path,
):
    """Same crash, but Telegram reports the message gone: the
    attempt is dropped and a fresh publish is allowed."""
    db_path = str(tmp_path / "publication.db")
    seed(db_path, status="SENDING", published_at=STALE, message_id=42)

    service = PublicationService(
        publisher=CountingPublisher(),
        repository=PublicationRepository(db_path),
        verifier=VerdictVerifier(Verdict.ABSENT),
    )
    assert service.verify_channel_attempts(now=NOW) == 1
    assert rows(db_path) == []

    publisher = CountingPublisher(message_id=3)
    outcome = PublicationService(
        publisher=publisher,
        repository=PublicationRepository(db_path),
    ).publish(build_deal(), now=NOW)

    assert outcome.success is True
    assert publisher.calls == ["123"]
    assert statuses(db_path) == ["PUBLISHED"]


def test_crash_during_verify_write_is_retried_next_run(
    tmp_path,
):
    db_path = str(tmp_path / "publication.db")
    seed(db_path, status="RECONCILIATION", published_at=STALE, message_id=42)

    repository = PublicationRepository(db_path)
    repository._connection = FailingConnection(
        repository._connection,
        # _apply_published_state is the only UPDATE that touches
        # published_at (T3b); T3a must still succeed
        fail_when=lambda sql: sql.strip().startswith("UPDATE")
        and "published_at" in sql,
    )
    service = PublicationService(
        publisher=CountingPublisher(),
        repository=repository,
        verifier=VerdictVerifier(Verdict.EXISTS),
    )

    first = service.verify_channel_attempts(now=NOW)
    assert first == 0
    assert statuses(db_path) == ["RECONCILIATION"]

    healthy = PublicationService(
        publisher=CountingPublisher(),
        repository=PublicationRepository(db_path),
        verifier=VerdictVerifier(Verdict.EXISTS),
    )
    second = healthy.verify_channel_attempts(now=NOW)

    assert second == 1
    assert statuses(db_path) == ["PUBLISHED"]


def test_crash_during_reconcile_write_is_retried_next_run(
    tmp_path,
):
    db_path = str(tmp_path / "publication.db")
    seed(db_path, status="SENDING", published_at=STALE)

    repository = PublicationRepository(db_path)
    repository._connection = FailingConnection(
        repository._connection,
        fail_when=lambda sql: sql.strip().startswith(
            "UPDATE"
        ),
    )

    # same window the service uses: now - STALE_ATTEMPT_SECONDS
    cutoff = STALE + timedelta(seconds=1)

    with pytest.raises(sqlite3.OperationalError):
        repository.reconcile_stale_attempts(
            older_than=cutoff
        )

    # the failed run left the row untouched
    assert statuses(db_path) == ["SENDING"]

    healthy = PublicationRepository(db_path)
    reconciled = healthy.reconcile_stale_attempts(
        older_than=cutoff
    )

    assert reconciled == 1
    assert statuses(db_path) == ["RECONCILIATION"]


def test_crash_after_persisted_publication_never_republishes(
    tmp_path,
):
    """Full healthy point: PUBLISHED committed. Every later run
    (verify, reconcile, publish) must leave it alone."""
    db_path = str(tmp_path / "publication.db")
    seed(
        db_path,
        status="PUBLISHED",
        published_at=NOW - timedelta(hours=1),
        message_id=77,
    )

    publisher = CountingPublisher()
    service = PublicationService(
        publisher=publisher,
        repository=PublicationRepository(db_path),
        verifier=VerdictVerifier(Verdict.ABSENT),
    )

    assert service.verify_channel_attempts(now=NOW) == 0
    assert service.reconcile_stale_attempts(now=NOW) == 0

    outcome = service.publish(build_deal(), now=NOW)

    assert outcome.status == "DUPLICATE_PUBLICATION"
    assert publisher.calls == []
    assert rows(db_path) == [
        (
            "PUBLISHED",
            (NOW - timedelta(hours=1)).isoformat(),
            77,
        )
    ]


def test_fail_closed_publisher_never_runs_without_a_row(
    tmp_path,
):
    """The moment publisher.publish() executes, a committed row
    must already be visible to an outside connection."""
    db_path = str(tmp_path / "publication.db")
    seen = {}

    class ProbePublisher:
        def publish(self, deal):
            connection = sqlite3.connect(db_path)

            try:
                seen["rows"] = connection.execute(
                    "SELECT status FROM publications "
                    "WHERE product_id = ?",
                    (deal.product.product_id,),
                ).fetchall()
            finally:
                connection.close()

            return PublicationResult(
                success=True,
                status="PUBLISHED",
                reason="Published.",
                message_id=1,
            )

    repository = PublicationRepository(db_path)
    # schema is created by the repository above; use a fresh
    # connection from this thread for the run itself
    repository.close()
    service = PublicationService(
        publisher=ProbePublisher(),
        repository=PublicationRepository(db_path),
    )
    outcome = service.publish(build_deal(), now=NOW)

    assert outcome.success is True
    assert seen["rows"] == [("SENDING",)]
