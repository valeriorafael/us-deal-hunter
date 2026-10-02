"""Phase 5 - Fase B: deterministic concurrency scenarios.

Every test here uses events/barriers as the only synchronisation.
There are no timing sleeps hoping for a race: the interleavings
are forced, so a broken H1 (BEGIN IMMEDIATE) or a lost update in
verify/reconcile fails deterministically.
"""

import sqlite3
import threading
from datetime import datetime, timedelta

from app.publication.base import PublicationResult, Verdict
from app.publication.service import PublicationService
from app.services.publication_repository import (
    PublicationRepository,
)


NOW = datetime(2026, 8, 15, 12, 0)
STALE = NOW - timedelta(seconds=601)
FRESH = NOW - timedelta(seconds=1)


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


def fetch_rows(db_path, product_id=None):
    connection = sqlite3.connect(db_path)

    try:
        if product_id is None:
            return connection.execute(
                "SELECT product_id, status, message_id "
                "FROM publications ORDER BY id"
            ).fetchall()

        return connection.execute(
            "SELECT product_id, status, message_id "
            "FROM publications WHERE product_id = ? ORDER BY id",
            (product_id,),
        ).fetchall()
    finally:
        connection.close()


class GatedPublisher:
    """Blocks inside publish() until released; asserts the row is
    already SENDING from a *separate* connection (fail-closed)."""

    def __init__(self, db_path, *, message_id=7):
        self.db_path = db_path
        self.message_id = message_id
        self.calls = []
        self.inside = threading.Event()
        self.release = threading.Event()
        self.status_when_called = None
        self.error = None

    def publish(self, deal):
        connection = sqlite3.connect(self.db_path)

        try:
            row = connection.execute(
                "SELECT status FROM publications "
                "WHERE product_id = ? ORDER BY id DESC LIMIT 1",
                (deal.product.product_id,),
            ).fetchone()
            self.status_when_called = row[0] if row else None
        finally:
            connection.close()

        self.calls.append(deal.product.product_id)
        self.inside.set()

        if not self.release.wait(timeout=10):
            raise AssertionError("release event never fired")

        return PublicationResult(
            success=True,
            status="PUBLISHED",
            reason="Published.",
            message_id=self.message_id,
        )


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


class ExistsVerifier:
    def __init__(self):
        self.calls = []

    def verify_message(self, message_id, *, affiliate_url):
        self.calls.append(message_id)
        return Verdict.EXISTS


def run_in_thread(target):
    errors = []
    results = []

    def wrapper():
        try:
            results.append(target())
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=wrapper)
    thread.start()

    return thread, results, errors


def join_all(threads, timeout=30):
    for thread in threads:
        thread.join(timeout=timeout)

    assert all(
        not thread.is_alive() for thread in threads
    ), "thread did not finish in time"


# ---------------------------------------------------------------------------
# B1 - two publish() for the same product
# ---------------------------------------------------------------------------


def test_b1_single_winner_single_row_single_send(tmp_path):
    db_path = str(tmp_path / "publication.db")
    # create schema first so only the publish race remains;
    # the concurrent-migration race has its own test below
    PublicationRepository(db_path).close()

    publisher = CountingPublisher(message_id=1)
    barrier = threading.Barrier(2, timeout=10)
    outcomes = [None, None]
    errors = []

    def worker(index):
        try:
            repository = PublicationRepository(db_path)
            service = PublicationService(
                publisher=publisher,
                repository=repository,
            )
            barrier.wait()
            outcomes[index] = service.publish(build_deal(), now=NOW)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(0,)),
        threading.Thread(target=worker, args=(1,)),
    ]

    for thread in threads:
        thread.start()

    join_all(threads)

    assert errors == []
    assert outcomes[0] is not None and outcomes[1] is not None

    successes = [r for r in outcomes if r.success]
    duplicates = [
        r
        for r in outcomes
        if r.status == "DUPLICATE_PUBLICATION"
    ]

    assert len(successes) == 1
    assert len(duplicates) == 1
    assert publisher.calls == ["123"]

    rows = fetch_rows(db_path, "123")
    assert len(rows) == 1
    assert rows[0][1] == "PUBLISHED"
    assert rows[0][2] == 1


# ---------------------------------------------------------------------------
# B2 - two independent connections / BEGIN IMMEDIATE
# ---------------------------------------------------------------------------


def test_b2_independent_connections_serialize_the_check(
    tmp_path,
):
    db_path = str(tmp_path / "publication.db")
    # create schema first so only the check/insert race remains
    PublicationRepository(db_path).close()

    a_in_check = threading.Event()
    release_a = threading.Event()
    b_started = threading.Event()
    b_done = threading.Event()

    a_result = {}
    b_result = {}
    errors = []

    def worker_a():
        try:
            repository = PublicationRepository(db_path)

            def blocking_check():
                a_in_check.set()

                if not release_a.wait(timeout=10):
                    raise AssertionError(
                        "release event never fired"
                    )

                return False

            a_result["id"] = repository.begin_attempt_exclusive(
                duplicate_check=blocking_check,
                product_id="123",
                affiliate_url="https://example.com",
                price=75.0,
                attempted_at=NOW,
            )
        except BaseException as exc:
            errors.append(exc)

    def worker_b():
        try:
            b_started.set()
            repository = PublicationRepository(db_path)

            b_result["id"] = repository.begin_attempt_exclusive(
                duplicate_check=lambda: (
                    repository.has_inflight_attempt("123")
                ),
                product_id="123",
                affiliate_url="https://example.com",
                price=75.0,
                attempted_at=NOW,
            )
        except BaseException as exc:
            errors.append(exc)
        finally:
            b_done.set()

    thread_a, _, _ = run_in_thread(worker_a)
    assert a_in_check.wait(timeout=10), "A never reached the check"

    thread_b, _, _ = run_in_thread(worker_b)
    assert b_started.wait(timeout=10), "B never started"

    try:
        # while A holds the write lock B must NOT be able to
        # finish its check-and-insert; otherwise BEGIN IMMEDIATE
        # is broken
        assert not b_done.wait(timeout=0.5), (
            "B completed while A held the write lock"
        )
    finally:
        release_a.set()

    join_all([thread_a, thread_b])

    assert errors == []
    assert a_result["id"] is not None
    assert b_result["id"] is None

    rows = fetch_rows(db_path, "123")
    assert len(rows) == 1
    assert rows[0][1] == "PENDING"


# ---------------------------------------------------------------------------
# B3 - concurrency during PENDING / SENDING / PUBLISHED /
#      RECONCILIATION
# ---------------------------------------------------------------------------


def test_b3_publish_blocked_while_sending_is_in_flight(
    tmp_path,
):
    db_path = str(tmp_path / "publication.db")
    # schema first (main thread), then connections per thread:
    # sqlite3 objects are thread-affine
    PublicationRepository(db_path).close()
    gated = GatedPublisher(db_path, message_id=7)

    def worker_a():
        repository_a = PublicationRepository(db_path)
        service_a = PublicationService(
            publisher=gated,
            repository=repository_a,
        )
        return service_a.publish(build_deal(), now=NOW)

    thread_a, results_a, errors_a = run_in_thread(worker_a)

    assert gated.inside.wait(timeout=10)
    assert gated.status_when_called == "SENDING"

    # a second, independent connection must see the in-flight
    # attempt and refuse to publish again
    repository_b = PublicationRepository(db_path)
    service_b = PublicationService(
        publisher=CountingPublisher(),
        repository=repository_b,
    )
    outcome_b = service_b.publish(build_deal(), now=NOW)

    assert outcome_b.success is False
    assert outcome_b.status == "DUPLICATE_PUBLICATION"
    assert fetch_rows(db_path, "123") == [("123", "SENDING", None)]

    gated.release.set()
    join_all([thread_a])

    assert errors_a == []
    assert results_a[0].success is True
    assert fetch_rows(db_path, "123") == [("123", "PUBLISHED", 7)]


def test_b3_publish_blocked_while_pending_row_exists(tmp_path):
    db_path = str(tmp_path / "publication.db")
    repository = PublicationRepository(db_path)
    repository.begin_attempt(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        attempted_at=NOW,
    )

    publisher = CountingPublisher()
    service = PublicationService(
        publisher=publisher,
        repository=repository,
    )

    outcome = service.publish(build_deal(), now=NOW)

    assert outcome.status == "DUPLICATE_PUBLICATION"
    assert publisher.calls == []
    assert fetch_rows(db_path, "123") == [
        ("123", "PENDING", None)
    ]


def test_b3_recent_published_row_blocks_new_send(tmp_path):
    db_path = str(tmp_path / "publication.db")
    repository = PublicationRepository(db_path)
    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=NOW - timedelta(minutes=5),
        status="PUBLISHED",
        message_id=99,
    )

    publisher = CountingPublisher()
    service = PublicationService(
        publisher=publisher,
        repository=repository,
    )

    outcome = service.publish(build_deal(), now=NOW)

    assert outcome.status == "DUPLICATE_PUBLICATION"
    assert publisher.calls == []


def test_b3_reconciliation_row_documents_at_least_once(
    tmp_path,
):
    """Spec 16: only PUBLISHED blocks the cooldown window.

    A RECONCILIATION row is an unknown outcome; the spec keeps
    publication at-least-once, so a new attempt is allowed. This
    test pins that product decision so a future change to
    has_inflight_attempt is deliberate.
    """
    db_path = str(tmp_path / "publication.db")
    repository = PublicationRepository(db_path)
    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=STALE,
        status="RECONCILIATION",
        message_id=42,
    )

    publisher = CountingPublisher(message_id=7)
    service = PublicationService(
        publisher=publisher,
        repository=repository,
        verifier=ExistsVerifier(),
    )

    outcome = service.publish(build_deal(), now=NOW)

    assert outcome.success is True
    assert publisher.calls == ["123"]
    rows = fetch_rows(db_path, "123")
    assert len(rows) == 2
    assert rows[0][1] == "RECONCILIATION"
    assert rows[1][1] == "PUBLISHED"


# ---------------------------------------------------------------------------
# B4 - verify_channel_attempts() vs reconcile_stale_attempts()
# ---------------------------------------------------------------------------


def test_b4_reconcile_then_verify_converges_to_published(
    tmp_path,
):
    db_path = str(tmp_path / "publication.db")
    repository = PublicationRepository(db_path)
    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=STALE,
        status="SENDING",
        message_id=42,
    )

    service = PublicationService(
        publisher=CountingPublisher(),
        repository=repository,
        verifier=ExistsVerifier(),
    )

    reconciled = service.reconcile_stale_attempts(now=NOW)
    verified = service.verify_channel_attempts(now=NOW)

    assert reconciled == 1
    assert verified == 1
    assert fetch_rows(db_path, "123") == [
        ("123", "PUBLISHED", 42)
    ]


def test_b4_verify_paused_across_a_concurrent_reconcile(
    tmp_path,
):
    """verify reads the row, reconcile flips it to
    RECONCILIATION, then verify promotes it: no lost update."""
    db_path = str(tmp_path / "publication.db")
    repository = PublicationRepository(db_path)
    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=STALE,
        status="SENDING",
        message_id=42,
    )

    repository.close()

    read_lock = threading.Event()
    release_verify = threading.Event()

    def worker_verify():
        own_repo = PublicationRepository(db_path)
        original = own_repo.attempts_for_verification

        def paused_read(**kwargs):
            records = original(**kwargs)
            read_lock.set()

            if not release_verify.wait(timeout=10):
                raise AssertionError(
                    "release event never fired"
                )

            return records

        own_repo.attempts_for_verification = paused_read

        service = PublicationService(
            publisher=CountingPublisher(),
            repository=own_repo,
            verifier=ExistsVerifier(),
        )
        return service.verify_channel_attempts(now=NOW)

    thread, results, errors = run_in_thread(worker_verify)

    assert read_lock.wait(timeout=10)

    # separate connection reconciles while verify is in-flight
    other = PublicationRepository(db_path)
    reconciled = PublicationService(
        publisher=CountingPublisher(),
        repository=other,
    ).reconcile_stale_attempts(now=NOW)
    assert reconciled == 1
    assert fetch_rows(db_path, "123") == [
        ("123", "RECONCILIATION", 42)
    ]

    release_verify.set()
    join_all([thread])

    assert errors == []
    assert results[0] == 1
    assert fetch_rows(db_path, "123") == [
        ("123", "PUBLISHED", 42)
    ]


def test_b4_reconcile_never_demotes_a_published_row(tmp_path):
    db_path = str(tmp_path / "publication.db")
    repository = PublicationRepository(db_path)
    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=STALE,
        status="PUBLISHED",
        message_id=42,
    )

    service = PublicationService(
        publisher=CountingPublisher(),
        repository=repository,
    )
    reconciled = service.reconcile_stale_attempts(now=NOW)

    assert reconciled == 0
    assert fetch_rows(db_path, "123") == [
        ("123", "PUBLISHED", 42)
    ]


# ---------------------------------------------------------------------------
# B5 - verify_channel_attempts() vs publish()
# ---------------------------------------------------------------------------


def test_b5_verify_first_blocks_the_new_publish(tmp_path):
    """Runner order: verification runs before publishing, so a
    message the channel still has turns into a cooldown hit."""
    db_path = str(tmp_path / "publication.db")
    repository = PublicationRepository(db_path)
    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=STALE,
        status="RECONCILIATION",
        message_id=42,
    )

    publisher = CountingPublisher()
    service = PublicationService(
        publisher=publisher,
        repository=repository,
        verifier=ExistsVerifier(),
    )

    verified = service.verify_channel_attempts(now=NOW)
    outcome = service.publish(build_deal(), now=NOW)

    assert verified == 1
    assert outcome.status == "DUPLICATE_PUBLICATION"
    assert publisher.calls == []
    assert fetch_rows(db_path, "123") == [
        ("123", "PUBLISHED", 42)
    ]


def test_b5_publish_during_a_paused_verification(tmp_path):
    """Cross-process window: a publish that slips in before the
    promotion is allowed by spec 16 (at-least-once) and must not
    corrupt either row. The in-process runner order (verify ->
    publish) closes this window; this test proves both writers
    converge without errors or lost rows."""
    db_path = str(tmp_path / "publication.db")
    repository = PublicationRepository(db_path)
    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=STALE,
        status="RECONCILIATION",
        message_id=42,
    )

    repository.close()

    read_lock = threading.Event()
    release_verify = threading.Event()

    def worker_verify():
        own_repo = PublicationRepository(db_path)
        original = own_repo.attempts_for_verification

        def paused_read(**kwargs):
            records = original(**kwargs)
            read_lock.set()

            if not release_verify.wait(timeout=10):
                raise AssertionError(
                    "release event never fired"
                )

            return records

        own_repo.attempts_for_verification = paused_read

        verify_service = PublicationService(
            publisher=CountingPublisher(),
            repository=own_repo,
            verifier=ExistsVerifier(),
        )
        return verify_service.verify_channel_attempts(now=NOW)

    thread, results, errors = run_in_thread(worker_verify)

    assert read_lock.wait(timeout=10)

    other = PublicationRepository(db_path)
    publish_publisher = CountingPublisher(message_id=9)
    publish_outcome = PublicationService(
        publisher=publish_publisher,
        repository=other,
    ).publish(build_deal(), now=NOW)

    assert publish_outcome.success is True
    assert publish_publisher.calls == ["123"]

    release_verify.set()
    join_all([thread])

    assert errors == []
    assert results[0] == 1

    rows = fetch_rows(db_path, "123")
    assert len(rows) == 2
    assert rows[0] == ("123", "PUBLISHED", 42)
    assert rows[1] == ("123", "PUBLISHED", 9)

    # the cooldown still holds after the interleaving
    final_publisher = CountingPublisher()
    blocked = PublicationService(
        publisher=final_publisher,
        repository=PublicationRepository(db_path),
    ).publish(build_deal(), now=NOW)

    assert blocked.status == "DUPLICATE_PUBLICATION"
    assert final_publisher.calls == []


# ---------------------------------------------------------------------------
# B6 - attempts_for_verification() under concurrency
# ---------------------------------------------------------------------------


def test_b6_double_verification_of_the_same_row_is_idempotent(
    tmp_path,
):
    db_path = str(tmp_path / "publication.db")
    repository = PublicationRepository(db_path)
    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=STALE,
        status="SENDING",
        message_id=42,
    )

    barrier = threading.Barrier(2, timeout=10)
    outcomes = [None, None]
    errors = []

    def worker(index):
        try:
            own_repo = PublicationRepository(db_path)
            service = PublicationService(
                publisher=CountingPublisher(),
                repository=own_repo,
                verifier=ExistsVerifier(),
            )
            barrier.wait()
            outcomes[index] = service.verify_channel_attempts(
                now=NOW
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(0,)),
        threading.Thread(target=worker, args=(1,)),
    ]

    for thread in threads:
        thread.start()

    join_all(threads)

    assert errors == []
    assert sum(outcomes) >= 1
    assert max(outcomes) == 1
    assert fetch_rows(db_path, "123") == [
        ("123", "PUBLISHED", 42)
    ]


def test_b6_verification_and_drop_race_stay_consistent(
    tmp_path,
):
    """Two connections verify the same row with opposite
    verdicts; whichever write lands last wins and the table
    never ends up with a half-updated row."""
    db_path = str(tmp_path / "publication.db")

    def seed():
        repository = PublicationRepository(db_path)
        repository.record(
            product_id="123",
            affiliate_url="https://example.com",
            price=75.0,
            published_at=STALE,
            status="RECONCILIATION",
            message_id=42,
        )
        repository.close()

    seed()

    class AbsentVerifier:
        def verify_message(self, message_id, *, affiliate_url):
            return Verdict.ABSENT

    barrier = threading.Barrier(2, timeout=10)
    errors = []
    results = [None, None]

    def worker(index, verifier):
        try:
            own_repo = PublicationRepository(db_path)
            service = PublicationService(
                publisher=CountingPublisher(),
                repository=own_repo,
                verifier=verifier,
            )
            barrier.wait()
            results[index] = service.verify_channel_attempts(
                now=NOW
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(
            target=worker, args=(0, ExistsVerifier())
        ),
        threading.Thread(
            target=worker, args=(1, AbsentVerifier())
        ),
    ]

    for thread in threads:
        thread.start()

    join_all(threads)

    assert errors == []
    assert all(result is not None for result in results)

    rows = fetch_rows(db_path, "123")
    # last writer wins: promoted or dropped, never corrupted
    assert rows in ([], [("123", "PUBLISHED", 42)])


# ---------------------------------------------------------------------------
# Concurrent startup on a fresh database (found by Fase 5 stress runs:
# both openers used to apply the same ALTER TABLE and one crashed
# with "duplicate column name: message_id")
# ---------------------------------------------------------------------------


def test_concurrent_connects_on_a_fresh_database_both_succeed(
    tmp_path,
):
    from app.services import database

    db_path = str(tmp_path / "fresh.db")
    barrier = threading.Barrier(2, timeout=10)
    errors = []

    def opener():
        try:
            barrier.wait()
            connection = database.connect(db_path)

            try:
                connection.execute(
                    "SELECT COUNT(*) FROM publications"
                ).fetchone()
            finally:
                connection.close()
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=opener),
        threading.Thread(target=opener),
    ]

    for thread in threads:
        thread.start()

    join_all(threads)

    assert errors == []

    connection = sqlite3.connect(db_path)

    try:
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(publications)"
            )
        }
    finally:
        connection.close()

    assert version == database.LATEST_SCHEMA_VERSION
    assert "message_id" in columns
