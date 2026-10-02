"""Phase 5 - Fase L: full multi-run integration flows.

Each test walks a complete story from the mission script (crash
after send, indeterminate telegram, absent recovery, curated
equivalence) and pins the cross-run invariants (fail-closed,
cooldown, sanitization).
"""

import sqlite3
import threading
from argparse import Namespace
from datetime import datetime, timedelta
from types import SimpleNamespace

import app.runner as runner_module
import app.services.curated_deals as curated_deals
from app.publication.base import PublicationResult, Verdict
from app.publication.service import PublicationService
from app.services.publication_repository import (
    PublicationRepository,
)

NOW = datetime(2026, 8, 15, 12, 0)
STALE = NOW - timedelta(seconds=601)


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


class Publisher:
    def __init__(self, *, mode="ok", message_id=7):
        self.mode = mode
        self.message_id = message_id
        self.calls = []

    def publish(self, deal):
        self.calls.append(deal.product.product_id)

        if self.mode == "indeterminate":
            return PublicationResult(
                success=False,
                status="TELEGRAM_REQUEST_ERROR",
                reason="HTTPSConnectionPool timeout",
                indeterminate=True,
            )

        return PublicationResult(
            success=True,
            status="PUBLISHED",
            reason="Published.",
            message_id=self.message_id,
        )


class VerdictVerifier:
    def __init__(self, verdict=Verdict.EXISTS):
        self.verdict = verdict
        self.calls = []

    def verify_message(self, message_id, *, affiliate_url):
        self.calls.append(message_id)
        return self.verdict


# ---------------------------------------------------------------------------
# Crash after send -> next run verification -> PUBLISHED
# ---------------------------------------------------------------------------


def test_flow_crash_after_send_recovers_without_duplicates(
    tmp_path,
):
    db_path = str(tmp_path / "publication.db")

    # run 1: message accepted, T3b crashes (row keeps SENDING+id)
    run1_publisher = Publisher(message_id=42)

    class T3bCrash(PublicationRepository):
        def _apply_published_state(
            self, attempt_id, published_at
        ):
            raise sqlite3.OperationalError(
                "database is locked"
            )

    run1 = PublicationService(
        publisher=run1_publisher,
        repository=T3bCrash(db_path),
    )
    outcome1 = run1.publish(build_deal(), now=NOW)

    # the operator still saw success (the message exists)
    assert outcome1.success is True
    assert rows(db_path) == [
        ("SENDING", NOW.isoformat(), 42)
    ]

    # run 2 (later): verification restores the truth
    later = NOW + timedelta(seconds=601)
    verifier = VerdictVerifier(Verdict.EXISTS)
    run2 = PublicationService(
        publisher=Publisher(),
        repository=PublicationRepository(db_path),
        verifier=verifier,
    )
    assert run2.verify_channel_attempts(now=later) == 1
    assert verifier.calls == [42]
    assert rows(db_path) == [
        ("PUBLISHED", NOW.isoformat(), 42)
    ]

    # run 3: cooldown blocks, nothing is sent again
    publisher3 = Publisher()
    run3 = PublicationService(
        publisher=publisher3,
        repository=PublicationRepository(db_path),
    )
    outcome3 = run3.publish(build_deal(), now=later)

    assert outcome3.status == "DUPLICATE_PUBLICATION"
    assert publisher3.calls == []
    assert len(rows(db_path)) == 1


# ---------------------------------------------------------------------------
# Indeterminate telegram -> RECONCILIATION -> retry next run
# ---------------------------------------------------------------------------


def test_flow_indeterminate_result_reconciles_then_retries(
    tmp_path,
):
    db_path = str(tmp_path / "publication.db")

    publisher1 = Publisher(mode="indeterminate")
    run1 = PublicationService(
        publisher=publisher1,
        repository=PublicationRepository(db_path),
    )
    outcome1 = run1.publish(build_deal(), now=NOW)

    assert outcome1.indeterminate is True
    assert rows(db_path) == [
        ("RECONCILIATION", NOW.isoformat(), None)
    ]

    # run 2: nothing can be probed (no message id); the product
    # is free again per spec 16 (at-least-once)
    verifier = VerdictVerifier(Verdict.EXISTS)
    publisher2 = Publisher(message_id=8)
    run2 = PublicationService(
        publisher=publisher2,
        repository=PublicationRepository(db_path),
        verifier=verifier,
    )
    assert run2.verify_channel_attempts(now=NOW) == 0
    assert verifier.calls == []
    assert run2.reconcile_stale_attempts(now=NOW) == 0

    outcome2 = run2.publish(build_deal(), now=NOW)

    assert outcome2.success is True
    assert publisher2.calls == ["123"]
    assert rows(db_path) == [
        ("RECONCILIATION", NOW.isoformat(), None),
        ("PUBLISHED", NOW.isoformat(), 8),
    ]

    # run 3: blocked by the fresh PUBLISHED row
    publisher3 = Publisher()
    run3 = PublicationService(
        publisher=publisher3,
        repository=PublicationRepository(db_path),
    )
    assert (
        run3.publish(build_deal(), now=NOW).status
        == "DUPLICATE_PUBLICATION"
    )
    assert publisher3.calls == []


# ---------------------------------------------------------------------------
# ABSENT -> row dropped -> new publish allowed
# ---------------------------------------------------------------------------


def test_flow_absent_frees_the_product_for_a_new_send(
    tmp_path,
):
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

    verifier = VerdictVerifier(Verdict.ABSENT)
    run1 = PublicationService(
        publisher=Publisher(),
        repository=PublicationRepository(db_path),
        verifier=verifier,
    )
    assert run1.verify_channel_attempts(now=NOW) == 1
    assert rows(db_path) == []

    publisher2 = Publisher(message_id=6)
    run2 = PublicationService(
        publisher=publisher2,
        repository=PublicationRepository(db_path),
    )
    outcome2 = run2.publish(build_deal(), now=NOW)

    assert outcome2.success is True
    assert publisher2.calls == ["123"]
    assert rows(db_path) == [
        ("PUBLISHED", NOW.isoformat(), 6)
    ]


# ---------------------------------------------------------------------------
# Curated equivalence
# ---------------------------------------------------------------------------


def build_runner_deal(product_id):
    from app.models.deal import Deal
    from app.models.product import Product

    return Deal(
        product=Product(
            product_id=product_id,
            title=f"Product {product_id}",
            current_price=75.0,
            average_price_30d=100.0,
            lowest_price_90d=70.0,
            rating=4.7,
            review_count=8500,
            platform="amazon",
            affiliate_url=(
                f"https://www.amazon.com/dp/{product_id}"
                "?tag=test-20"
            ),
        ),
        score=0.0,
        label="CURATED",
        confidence="VERIFIED",
        reference_price=100.0,
        source_name="Example Wire",
    )


def test_flow_curated_runs_verification_reconcile_and_summary(
    tmp_path,
    monkeypatch,
    capsys,
):
    """The curated path must run the same verify -> reconcile ->
    publish pipeline and print the same SUMMARY lines."""
    db_path = str(tmp_path / "curated.db")

    seeded = PublicationRepository(db_path)
    seeded.record(
        product_id="B0STALE1",
        affiliate_url=(
            "https://www.amazon.com/dp/B0STALE1?tag=test-20"
        ),
        price=75.0,
        published_at=datetime.now() - timedelta(seconds=601),
        status="SENDING",
        message_id=42,
    )
    seeded.close()

    class FakePublisher:
        def __init__(self):
            self.sent = []

        def publish(self, deal):
            self.sent.append(deal.product.product_id)

            return PublicationResult(
                success=True,
                status="PUBLISHED",
                reason="Published.",
                message_id=9,
            )

        def verify_message(self, message_id, *, affiliate_url):
            assert message_id == 42
            return Verdict.EXISTS

    publisher = FakePublisher()

    class FakeTelegramConfig:
        @classmethod
        def from_environment(cls):
            return cls()

        def create_publisher(self):
            return publisher

    class FakeCuratedDealLoader:
        def load(self, path=None):
            return SimpleNamespace(
                deals=[build_runner_deal("B0CUR9")],
                max_publications_per_run=3,
            )

    class FakePublicationRepository:
        def __init__(self, *args, **kwargs):
            self._handle = PublicationRepository(db_path)

        def __getattr__(self, name):
            return getattr(self._handle, name)

    monkeypatch.setattr(
        runner_module,
        "TelegramConfig",
        FakeTelegramConfig,
    )
    monkeypatch.setattr(
        runner_module,
        "PublicationRepository",
        FakePublicationRepository,
    )
    monkeypatch.setattr(
        curated_deals,
        "CuratedDealLoader",
        FakeCuratedDealLoader,
    )

    code = runner_module.run(
        Namespace(
            keywords=None,
            search_index="All",
            item_count=10,
            item_page=1,
            min_saving_percent=None,
            max_publications=None,
            keywords_file=None,
            curated_file="data/curated_deals.json",
            dry_run=False,
            demo=False,
            publish_demo=False,
        )
    )

    out = capsys.readouterr().out
    stale_row = rows(db_path, "B0STALE1")
    fresh_row = rows(db_path, "B0CUR9")

    assert code == 0
    # stale attempt verified first
    assert "Channel verified: 1" in out
    assert "Reconciled unknown: 0" in out
    assert publisher.sent == ["B0CUR9"]
    assert stale_row == [
        (
            "PUBLISHED",
            stale_row[0][1],
            42,
        )
    ], stale_row
    assert len(fresh_row) == 1
    assert fresh_row[0][0] == "PUBLISHED"
    assert fresh_row[0][2] == 9
    assert "SUMMARY" in out
    assert "Publications successful: 1" in out
    assert "Publication complete: 1/1 published." in out


# ---------------------------------------------------------------------------
# K5 - secrets never reach the summary
# ---------------------------------------------------------------------------


def test_flow_bare_bot_token_never_reaches_the_summary(
    monkeypatch,
    capsys,
):
    secret = "9876543210:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    class ExplodingPublisher:
        def publish(self, deal):
            raise RuntimeError(
                "failed posting to "
                f"https://api.telegram.org/bot{secret}"
                "/sendMessage"
            )

    class FakeTelegramConfig:
        @classmethod
        def from_environment(cls):
            return cls()

        def create_publisher(self):
            return ExplodingPublisher()

    class FakeRepository:
        def __init__(self, *args, **kwargs):
            pass

        def begin_attempt_exclusive(self, **kwargs):
            return 1

        def mark_sending(self, attempt_id):
            pass

        def mark_unknown(self, attempt_id):
            pass

        def reconcile_stale_attempts(self, **kwargs):
            return 0

    class DealDiscovery:
        def __init__(self):
            self.product_errors = []

        def discover_deals(self, **kwargs):
            return [build_deal("B0LEAK1")]

    monkeypatch.setattr(
        runner_module,
        "build_discovery_workflow",
        lambda **kwargs: DealDiscovery(),
    )
    monkeypatch.setattr(
        runner_module,
        "build_keyword_configs",
        lambda args: (
            [
                runner_module.KeywordConfig(
                    query="mouse",
                    search_index="All",
                    item_count=10,
                    item_page=1,
                    min_saving_percent=None,
                )
            ],
            3,
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "TelegramConfig",
        FakeTelegramConfig,
    )
    monkeypatch.setattr(
        runner_module,
        "PublicationRepository",
        FakeRepository,
    )

    code = runner_module.run(
        Namespace(
            keywords="mouse",
            search_index="All",
            item_count=10,
            item_page=1,
            min_saving_percent=None,
            max_publications=None,
            keywords_file=None,
            curated_file=None,
            dry_run=False,
            demo=True,
            publish_demo=True,
        )
    )

    out = capsys.readouterr().out

    assert code == 0
    assert secret not in out
    assert "bot[REDACTED]/" in out
    assert "[REDACTED]" in out
