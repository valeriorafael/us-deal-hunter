from datetime import datetime, timedelta

from app.models.deal import Deal
from app.models.product import Product
from app.publication.base import (
    DEFAULT_PUBLICATION_COOLDOWN,
    PublicationResult,
    Verdict,
)
from app.publication.service import PublicationService
from app.services.publication_repository import (
    PublicationRepository,
)


def build_valid_deal(product_id="123"):
    product = Product(
        product_id=product_id,
        title="Test Product",
        current_price=75.0,
        average_price_30d=100.0,
        lowest_price_90d=70.0,
        rating=4.7,
        review_count=8500,
        platform="amazon",
        affiliate_url=(
            f"https://www.amazon.com/dp/{product_id}?tag=test-20"
        ),
    )

    return Deal(
        product=product,
        score=88.0,
        label="GREAT",
        confidence="HIGH",
    )


def test_publication_service_publishes_valid_deal(tmp_path):
    captured = {}

    class FakePublisher:
        def publish(self, deal):
            captured["deal"] = deal

            return PublicationResult(
                success=True,
                status="PUBLISHED",
                reason="Published.",
                message_id=123,
            )

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    deal = build_valid_deal()

    result = PublicationService(
        publisher=FakePublisher(),
        repository=repository,
    ).publish(deal)

    assert result.success is True
    assert result.status == "PUBLISHED"
    assert result.message_id == 123
    assert captured["deal"] is deal


def test_publication_service_rejects_invalid_deal(tmp_path):
    class FakePublisher:
        def publish(self, deal):
            raise AssertionError(
                "Publisher should not be called."
            )

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    product = Product(
        product_id="123",
        title="Unknown Product",
        current_price=75.0,
        platform="amazon",
    )

    deal = Deal(
        product=product,
        score=10.0,
        label="WEAK",
        confidence="LOW",
    )

    result = PublicationService(
        publisher=FakePublisher(),
        repository=repository,
    ).publish(deal)

    assert result.success is False
    assert result.status == "INSUFFICIENT_HISTORY"


def test_publication_service_rejects_amazon_deal_without_affiliate_link(
    tmp_path,
):
    class FakePublisher:
        def publish(self, deal):
            raise AssertionError(
                "Publisher should not be called."
            )

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    product = Product(
        product_id="123",
        title="Amazon Product",
        current_price=75.0,
        average_price_30d=100.0,
        lowest_price_90d=70.0,
        rating=4.7,
        review_count=8500,
        platform="amazon",
    )

    deal = Deal(
        product=product,
        score=88.0,
        label="GREAT",
        confidence="HIGH",
    )

    result = PublicationService(
        publisher=FakePublisher(),
        repository=repository,
    ).publish(deal)

    assert result.success is False
    assert result.status == "MISSING_AFFILIATE_LINK"


def test_publication_service_propagates_publisher_failure(tmp_path):
    class FakePublisher:
        def publish(self, deal):
            return PublicationResult(
                success=False,
                status="TELEGRAM_API_ERROR",
                reason="Chat not found.",
            )

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    result = PublicationService(
        publisher=FakePublisher(),
        repository=repository,
    ).publish(build_valid_deal())

    assert result.success is False
    assert result.status == "TELEGRAM_API_ERROR"
    assert result.reason == "Chat not found."


def test_publication_service_blocks_recent_duplicate(tmp_path):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    repository.record(
        product_id="123",
        affiliate_url=(
            "https://www.amazon.com/dp/123?tag=test-20"
        ),
        price=75.0,
        published_at=now,
    )

    class FakePublisher:
        def publish(self, deal):
            raise AssertionError(
                "Publisher should not be called."
            )

    result = PublicationService(
        publisher=FakePublisher(),
        repository=repository,
    ).publish(
        build_valid_deal(),
        now=now,
    )

    assert result.success is False
    assert result.status == "DUPLICATE_PUBLICATION"


def test_publication_service_records_successful_publication(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    class FakePublisher:
        def publish(self, deal):
            return PublicationResult(
                success=True,
                status="PUBLISHED",
                reason="Published.",
                message_id=123,
            )

    result = PublicationService(
        publisher=FakePublisher(),
        repository=repository,
    ).publish(
        build_valid_deal(),
        now=now,
    )

    assert result.success is True
    assert repository.count("123") == 1
    assert repository.was_published_recently(
        "123",
        now=now,
    ) is True


def test_publication_service_is_agnostic_to_publisher_fallback(
    tmp_path,
):
    """
    The publisher owns the sendPhoto/sendMessage fallback.
    The service must call it once and record once.
    """
    calls = []

    class FakePublisher:
        def publish(self, deal):
            calls.append(deal.product.product_id)

            return PublicationResult(
                success=True,
                status="PUBLISHED",
                reason="Published.",
                message_id=333,
            )

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    result = PublicationService(
        publisher=FakePublisher(),
        repository=repository,
    ).publish(build_valid_deal())

    assert result.success is True
    assert calls == ["123"]

    # record once: exactly one row, exactly one send
    import sqlite3

    connection = sqlite3.connect(
        str(tmp_path / "publication.db")
    )

    try:
        stored = connection.execute(
            "SELECT product_id, status, message_id "
            "FROM publications"
        ).fetchall()
    finally:
        connection.close()

    assert stored == [("123", "PUBLISHED", 333)]
    assert repository.count("123") == 1


def test_publication_service_does_not_record_failed_fallback(
    tmp_path,
):
    class FakePublisher:
        def publish(self, deal):
            return PublicationResult(
                success=False,
                status="TELEGRAM_API_ERROR",
                reason="wrong file identifier",
            )

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    result = PublicationService(
        publisher=FakePublisher(),
        repository=repository,
    ).publish(build_valid_deal())

    assert result.success is False
    assert result.status == "TELEGRAM_API_ERROR"
    assert repository.count("123") == 0


class RecordingPublisher:
    def __init__(self, failures=0):
        self.calls = []
        self.failures = failures

    def publish(self, deal):
        self.calls.append(deal.product.product_id)

        if len(self.calls) <= self.failures:
            return PublicationResult(
                success=False,
                status="TELEGRAM_API_ERROR",
                reason="Telegram rejected the message.",
            )

        return PublicationResult(
            success=True,
            status="PUBLISHED",
            reason="Published.",
            message_id=len(self.calls),
        )


class ExplodingPublisher:
    def publish(self, deal):
        raise AssertionError(
            "Publisher must not be called."
        )


def test_a_unpublished_product_can_publish(tmp_path):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )
    publisher = RecordingPublisher()

    result = PublicationService(
        publisher=publisher,
        repository=repository,
    ).publish(build_valid_deal(), now=now)

    assert result.success is True
    assert publisher.calls == ["123"]
    assert repository.count("123") == 1


def test_b_published_product_never_reaches_telegram(tmp_path):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=now,
    )

    result = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
    ).publish(build_valid_deal(), now=now)

    assert result.success is False
    assert result.status == "DUPLICATE_PUBLICATION"


def test_c_failed_publication_can_be_retried(tmp_path):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    publisher = RecordingPublisher(failures=1)

    service = PublicationService(
        publisher=publisher,
        repository=repository,
    )

    first = service.publish(build_valid_deal(), now=now)

    assert first.success is False
    assert first.status == "TELEGRAM_API_ERROR"
    assert repository.count("123") == 0

    second = service.publish(
        build_valid_deal(),
        now=now + timedelta(minutes=5),
    )

    assert second.success is True
    assert publisher.calls == ["123", "123"]
    assert repository.count("123") == 1


def test_d_different_products_can_both_publish(tmp_path):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    publisher = RecordingPublisher()

    service = PublicationService(
        publisher=publisher,
        repository=repository,
    )

    first = service.publish(
        build_valid_deal(),
        now=now,
    )
    second = service.publish(
        build_valid_deal(product_id="456"),
        now=now,
    )

    assert first.success is True
    assert second.success is True
    assert publisher.calls == ["123", "456"]
    assert repository.count("123") == 1
    assert repository.count("456") == 1


def test_e_duplicate_blocked_on_second_run(tmp_path):
    db_path = str(tmp_path / "publication.db")
    first_run = datetime(2026, 8, 15, 2, 0)
    second_run = datetime(2026, 8, 15, 20, 0)

    publisher = RecordingPublisher()

    first_service = PublicationService(
        publisher=publisher,
        repository=PublicationRepository(db_path),
    )

    first = first_service.publish(
        build_valid_deal(),
        now=first_run,
    )

    second_service = PublicationService(
        publisher=publisher,
        repository=PublicationRepository(db_path),
    )

    second = second_service.publish(
        build_valid_deal(),
        now=second_run,
    )

    assert first.success is True
    assert second.success is False
    assert second.status == "DUPLICATE_PUBLICATION"
    assert publisher.calls == ["123"]


def test_g_republication_allowed_after_cooldown_elapsed(tmp_path):
    published_at = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=published_at,
    )

    publisher = RecordingPublisher()

    result = PublicationService(
        publisher=publisher,
        repository=repository,
    ).publish(
        build_valid_deal(),
        now=published_at + timedelta(hours=25),
    )

    assert result.success is True
    assert publisher.calls == ["123"]


def test_h_exactly_at_cooldown_boundary_can_publish(tmp_path):
    published_at = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=published_at,
    )

    publisher = RecordingPublisher()

    result = PublicationService(
        publisher=publisher,
        repository=repository,
    ).publish(
        build_valid_deal(),
        now=published_at + DEFAULT_PUBLICATION_COOLDOWN,
    )

    assert result.success is True
    assert publisher.calls == ["123"]


def test_i_one_second_before_cooldown_is_blocked(tmp_path):
    published_at = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=published_at,
    )

    result = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
    ).publish(
        build_valid_deal(),
        now=(
            published_at
            + DEFAULT_PUBLICATION_COOLDOWN
            - timedelta(seconds=1)
        ),
    )

    assert result.success is False
    assert result.status == "DUPLICATE_PUBLICATION"


def test_j_second_run_respects_cooldown_with_same_db(tmp_path):
    db_path = str(tmp_path / "publication.db")
    first_run = datetime(2026, 8, 15, 2, 0)

    publisher = RecordingPublisher()

    first_service = PublicationService(
        publisher=publisher,
        repository=PublicationRepository(db_path),
    )

    first = first_service.publish(
        build_valid_deal(),
        now=first_run,
    )

    second_service = PublicationService(
        publisher=publisher,
        repository=PublicationRepository(db_path),
    )

    blocked = second_service.publish(
        build_valid_deal(),
        now=first_run + timedelta(hours=1),
    )
    allowed = second_service.publish(
        build_valid_deal(),
        now=first_run + timedelta(hours=25),
    )

    assert first.success is True
    assert blocked.success is False
    assert blocked.status == "DUPLICATE_PUBLICATION"
    assert allowed.success is True
    assert publisher.calls == ["123", "123"]


def test_k_permanent_policy_still_available_when_requested(tmp_path):
    published_at = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=published_at,
    )

    publisher = RecordingPublisher()

    result = PublicationService(
        publisher=publisher,
        repository=repository,
        cooldown=None,
    ).publish(
        build_valid_deal(),
        now=published_at + timedelta(days=400),
    )

    assert result.success is False
    assert result.status == "DUPLICATE_PUBLICATION"
    assert publisher.calls == []


def test_default_cooldown_is_exactly_24_hours(tmp_path):
    assert DEFAULT_PUBLICATION_COOLDOWN == timedelta(
        hours=24
    )

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    service = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
    )

    assert service.cooldown == timedelta(hours=24)


def test_failed_prior_attempt_does_not_block_retry(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=now,
        status="FAILED",
    )

    publisher = RecordingPublisher()

    result = PublicationService(
        publisher=publisher,
        repository=repository,
    ).publish(
        build_valid_deal(),
        now=now + timedelta(minutes=5),
    )

    assert result.success is True
    assert publisher.calls == ["123"]
    assert repository.was_published("123") is True


def test_cooldown_none_allows_never_published_product(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    publisher = RecordingPublisher()

    result = PublicationService(
        publisher=publisher,
        repository=repository,
        cooldown=None,
    ).publish(build_valid_deal(), now=now)

    assert result.success is True
    assert publisher.calls == ["123"]
    assert repository.count("123") == 1


def test_cooldown_none_allows_retry_after_failure(
    tmp_path,
):
    published_at = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=published_at,
        status="FAILED",
    )

    publisher = RecordingPublisher()

    result = PublicationService(
        publisher=publisher,
        repository=repository,
        cooldown=None,
    ).publish(
        build_valid_deal(),
        now=published_at + timedelta(days=400),
    )

    assert result.success is True
    assert publisher.calls == ["123"]


def test_duplicate_result_reports_recent_publication(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=now,
    )

    result = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
    ).publish(
        build_valid_deal(),
        now=now + timedelta(hours=1),
    )

    assert result.success is False
    assert result.status == "DUPLICATE_PUBLICATION"
    assert (
        result.reason == "Product was published recently."
    )


def test_duplicate_result_reports_already_published(
    tmp_path,
):
    published_at = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=published_at,
    )

    result = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
        cooldown=None,
    ).publish(
        build_valid_deal(),
        now=published_at + timedelta(days=400),
    )

    assert result.success is False
    assert result.status == "DUPLICATE_PUBLICATION"
    assert (
        result.reason == "Product was already published."
    )


def _row_for(repository, product_id="123"):
    return repository._connection.execute(
        """
        SELECT id, status, published_at, message_id
        FROM publications
        WHERE product_id = ?
        ORDER BY id
        """,
        (product_id,),
    ).fetchall()


def test_success_persists_published_state_and_message_id(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )
    publisher = RecordingPublisher()

    result = PublicationService(
        publisher=publisher,
        repository=repository,
    ).publish(build_valid_deal(), now=now)

    rows = _row_for(repository)

    assert result.success is True
    assert result.message_id == 1
    assert len(rows) == 1
    assert rows[0][1] == "PUBLISHED"
    assert rows[0][2] == now.isoformat()
    assert rows[0][3] == 1


def test_indeterminate_failure_keeps_reconciliation_row(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)

    class IndeterminatePublisher:
        def publish(self, deal):
            return PublicationResult(
                success=False,
                status="TELEGRAM_REQUEST_ERROR",
                reason="timed out",
                indeterminate=True,
            )

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    result = PublicationService(
        publisher=IndeterminatePublisher(),
        repository=repository,
    ).publish(build_valid_deal(), now=now)

    rows = _row_for(repository)

    assert result.success is False
    assert result.indeterminate is True
    assert len(rows) == 1
    assert rows[0][1] == "RECONCILIATION"
    assert repository.was_published("123") is False
    assert (
        repository.was_published_recently(
            "123", now=now
        )
        is False
    )


def test_publisher_exception_becomes_publication_exception(
    tmp_path,
):
    import sqlite3  # noqa: F401  (keeps driver import local)

    now = datetime(2026, 8, 15, 12, 0)

    class ExplodingPublisher:
        def publish(self, deal):
            raise RuntimeError(
                "connection lost token=secret-value"
            )

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    result = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
    ).publish(build_valid_deal(), now=now)

    rows = _row_for(repository)

    assert result.success is False
    assert result.status == "PUBLICATION_EXCEPTION"
    assert result.indeterminate is True
    assert "secret-value" not in result.reason
    assert "token=[REDACTED]" in result.reason
    assert len(rows) == 1
    assert rows[0][1] == "RECONCILIATION"


class BrokenStoreRepository(PublicationRepository):
    def __init__(self, db_path, fail_on):
        super().__init__(db_path)
        self.fail_on = fail_on

    def begin_attempt(self, **kwargs):
        if self.fail_on == "begin_attempt":
            raise __import__("sqlite3").OperationalError(
                "disk I/O error"
            )

        return super().begin_attempt(**kwargs)

    def mark_sending(self, attempt_id):
        if self.fail_on == "mark_sending":
            raise __import__("sqlite3").OperationalError(
                "database is locked"
            )

        super().mark_sending(attempt_id)

    def mark_published(
        self, attempt_id, published_at, message_id=None
    ):
        if self.fail_on == "mark_published":
            raise __import__("sqlite3").OperationalError(
                "database is locked"
            )

        super().mark_published(
            attempt_id, published_at, message_id
        )


def test_store_error_before_sending_fails_closed(tmp_path):
    now = datetime(2026, 8, 15, 12, 0)

    repository = BrokenStoreRepository(
        str(tmp_path / "publication.db"),
        fail_on="begin_attempt",
    )

    result = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
    ).publish(build_valid_deal(), now=now)

    assert result.success is False
    assert result.status == "PUBLICATION_STORE_ERROR"
    assert "OperationalError" in result.reason
    # ExplodingPublisher would have raised AssertionError,
    # so STORE_ERROR proves the publisher was never called
    assert _row_for(repository) == []


def test_store_error_on_mark_sending_drops_attempt(tmp_path):
    now = datetime(2026, 8, 15, 12, 0)

    repository = BrokenStoreRepository(
        str(tmp_path / "publication.db"),
        fail_on="mark_sending",
    )

    result = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
    ).publish(build_valid_deal(), now=now)

    assert result.success is False
    assert result.status == "PUBLICATION_STORE_ERROR"
    assert _row_for(repository) == []


def test_store_error_after_success_still_reports_success(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)

    repository = BrokenStoreRepository(
        str(tmp_path / "publication.db"),
        fail_on="mark_published",
    )
    publisher = RecordingPublisher()

    result = PublicationService(
        publisher=publisher,
        repository=repository,
    ).publish(build_valid_deal(), now=now)

    rows = _row_for(repository)

    assert result.success is True
    assert result.message_id == 1
    assert len(rows) == 1
    # left for reconciliation on the next run
    assert rows[0][1] == "SENDING"
    assert rows[0][3] is None


def test_reconcile_stale_attempts_through_service(tmp_path):
    now = datetime(2026, 8, 15, 12, 0)

    class SilentPublisher:
        def publish(self, deal):
            raise AssertionError("not expected")

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )
    service = PublicationService(
        publisher=SilentPublisher(),
        repository=repository,
    )

    stale = repository.begin_attempt(
        product_id="A1",
        affiliate_url="https://example.com",
        price=10.0,
        attempted_at=now - timedelta(seconds=601),
    )
    repository.mark_sending(stale)

    fresh = repository.begin_attempt(
        product_id="A2",
        affiliate_url="https://example.com",
        price=10.0,
        attempted_at=now - timedelta(seconds=599),
    )
    repository.mark_sending(fresh)

    resolved = service.reconcile_stale_attempts(now)

    assert resolved == 1
    assert _row_for(repository, "A1")[0][1] == (
        "RECONCILIATION"
    )
    assert _row_for(repository, "A2")[0][1] == "SENDING"
    assert service.reconcile_stale_attempts(now) == 0


def test_reconciled_product_publishes_then_blocks_again(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )
    publisher = RecordingPublisher()
    service = PublicationService(
        publisher=publisher,
        repository=repository,
    )

    orphan = repository.begin_attempt(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        attempted_at=now - timedelta(seconds=601),
    )
    repository.mark_sending(orphan)

    assert service.reconcile_stale_attempts(now) == 1

    first = service.publish(build_valid_deal(), now=now)

    assert first.success is True
    assert publisher.calls == ["123"]
    assert len(_row_for(repository)) == 2

    second = service.publish(
        build_valid_deal(),
        now=now + timedelta(minutes=5),
    )

    assert second.success is False
    assert second.status == "DUPLICATE_PUBLICATION"
    assert publisher.calls == ["123"]


def test_store_error_after_success_is_reconciled_and_retried(
    tmp_path,
):
    """M4 crash window, end to end.

    mark_published fails after the message was delivered, so the
    row stays SENDING without message_id; the cooldown ignores it,
    the next run reconciles it to RECONCILIATION and the product
    can be published again (documented duplicate risk R1/M4).
    """
    now = datetime(2026, 8, 15, 12, 0)

    repository = BrokenStoreRepository(
        str(tmp_path / "publication.db"),
        fail_on="mark_published",
    )
    publisher = RecordingPublisher()
    service = PublicationService(
        publisher=publisher,
        repository=repository,
        cooldown=DEFAULT_PUBLICATION_COOLDOWN,
    )

    first = service.publish(build_valid_deal(), now=now)

    assert first.success is True
    rows = _row_for(repository)
    assert rows[0][1] == "SENDING"
    assert rows[0][3] is None
    assert (
        service._is_duplicate(
            build_valid_deal(),
            now + timedelta(seconds=1),
        )
        is False
    )

    later = now + timedelta(seconds=601)

    assert service.reconcile_stale_attempts(later) == 1
    assert _row_for(repository)[0][1] == "RECONCILIATION"

    repository.fail_on = "none"

    second = service.publish(build_valid_deal(), now=later)

    assert second.success is True
    assert publisher.calls == ["123", "123"]
    statuses = [row[1] for row in _row_for(repository)]
    assert statuses == ["RECONCILIATION", "PUBLISHED"]
    assert (
        service._is_duplicate(build_valid_deal(), later) is True
    )


class FakeVerifier:
    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = []

    def verify_message(self, message_id, *, affiliate_url):
        self.calls.append((message_id, affiliate_url))

        return self.verdict


def _seed_inflight_attempt(
    repository,
    published_at,
    status="SENDING",
    message_id=42,
):
    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=published_at,
        status=status,
        message_id=message_id,
    )


def test_verify_promotes_a_message_the_channel_still_has(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)
    stale = now - timedelta(seconds=601)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )
    _seed_inflight_attempt(repository, stale)

    verifier = FakeVerifier(Verdict.EXISTS)

    service = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
        verifier=verifier,
    )

    resolved = service.verify_channel_attempts(now)
    rows = _row_for(repository)

    assert resolved == 1
    assert verifier.calls == [(42, "https://example.com")]
    assert rows[0][1] == "PUBLISHED"
    # the cooldown counts from the real send time
    assert rows[0][2] == stale.isoformat()
    assert rows[0][3] == 42


def test_verify_drops_a_message_telegram_reports_deleted(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)
    stale = now - timedelta(seconds=601)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )
    _seed_inflight_attempt(repository, stale)

    verifier = FakeVerifier(Verdict.ABSENT)

    service = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
        verifier=verifier,
    )

    resolved = service.verify_channel_attempts(now)

    assert resolved == 1
    assert _row_for(repository) == []
    assert repository.count("123") == 0


def test_verify_keeps_unknown_outcomes_untouched(tmp_path):
    now = datetime(2026, 8, 15, 12, 0)
    stale = now - timedelta(seconds=601)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )
    _seed_inflight_attempt(repository, stale)

    verifier = FakeVerifier(Verdict.UNKNOWN)

    service = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
        verifier=verifier,
    )

    resolved = service.verify_channel_attempts(now)

    assert resolved == 0
    assert len(verifier.calls) == 1
    assert _row_for(repository)[0][1] == "SENDING"


def test_verify_without_a_verifier_does_nothing(tmp_path):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    service = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
    )

    assert service.verify_channel_attempts(now) == 0
    assert service.verifier is None


def test_verify_ignores_a_publisher_without_probe(tmp_path):
    now = datetime(2026, 8, 15, 12, 0)
    stale = now - timedelta(seconds=601)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )
    _seed_inflight_attempt(repository, stale)

    service = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
        verifier=object(),
    )

    assert service.verify_channel_attempts(now) == 0
    assert _row_for(repository)[0][1] == "SENDING"


def test_verify_survives_a_failing_probe(tmp_path):
    now = datetime(2026, 8, 15, 12, 0)
    stale = now - timedelta(seconds=601)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )
    _seed_inflight_attempt(repository, stale)

    class ExplodingVerifier:
        def verify_message(
            self, message_id, *, affiliate_url
        ):
            raise RuntimeError("probe failed token=abc123")

    service = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
        verifier=ExplodingVerifier(),
    )

    resolved = service.verify_channel_attempts(now)

    assert resolved == 0
    assert _row_for(repository)[0][1] == "SENDING"


def test_verify_ignores_attempts_without_message_id(tmp_path):
    now = datetime(2026, 8, 15, 12, 0)
    stale = now - timedelta(seconds=601)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )
    _seed_inflight_attempt(repository, stale, message_id=None)

    verifier = FakeVerifier(Verdict.EXISTS)

    service = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
        verifier=verifier,
    )

    resolved = service.verify_channel_attempts(now)

    assert resolved == 0
    assert verifier.calls == []
    assert _row_for(repository)[0][1] == "SENDING"


def test_verify_leaves_fresh_attempts_alone(tmp_path):
    now = datetime(2026, 8, 15, 12, 0)
    fresh = now - timedelta(seconds=599)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )
    _seed_inflight_attempt(repository, fresh)

    verifier = FakeVerifier(Verdict.EXISTS)

    service = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
        verifier=verifier,
    )

    resolved = service.verify_channel_attempts(now)

    assert resolved == 0
    assert verifier.calls == []
    assert _row_for(repository)[0][1] == "SENDING"


def test_verify_skips_attempts_outside_the_age_window(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)
    too_old = now - timedelta(hours=49)

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )
    _seed_inflight_attempt(repository, too_old)

    verifier = FakeVerifier(Verdict.EXISTS)

    service = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
        verifier=verifier,
    )

    resolved = service.verify_channel_attempts(now)

    assert resolved == 0
    assert verifier.calls == []
    assert _row_for(repository)[0][1] == "SENDING"


def test_message_id_survives_a_failure_before_the_state_change(
    tmp_path,
):
    """T3a/T3b window: the handle is committed before the status
    flip, so a crash there never loses the message reference."""
    now = datetime(2026, 8, 15, 12, 0)

    class T3bBrokenRepository(PublicationRepository):
        def _apply_published_state(
            self, attempt_id, published_at
        ):
            raise __import__("sqlite3").OperationalError(
                "database is locked"
            )

    repository = T3bBrokenRepository(
        str(tmp_path / "publication.db")
    )
    publisher = RecordingPublisher()

    result = PublicationService(
        publisher=publisher,
        repository=repository,
    ).publish(build_valid_deal(), now=now)

    rows = _row_for(repository)

    assert result.success is True
    assert len(rows) == 1
    assert rows[0][1] == "SENDING"
    assert rows[0][3] == 1


def test_concurrent_runs_never_double_publish(tmp_path):
    """H1: two runs racing on the same product must produce
    exactly one send."""
    import threading

    db_path = str(tmp_path / "publication.db")
    now = datetime(2026, 8, 15, 12, 0)

    PublicationRepository(db_path).close()

    barrier = threading.Barrier(2, timeout=10)
    publisher = RecordingPublisher()
    results = [None, None]
    errors = []

    def worker(index):
        repository = None

        try:
            repository = PublicationRepository(db_path)
            service = PublicationService(
                publisher=publisher,
                repository=repository,
            )

            barrier.wait()
            results[index] = service.publish(
                build_valid_deal(),
                now=now,
            )
        except Exception as exc:
            errors.append(exc)
        finally:
            if repository is not None:
                repository.close()

    threads = [
        threading.Thread(target=worker, args=(0,)),
        threading.Thread(target=worker, args=(1,)),
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert all(result is not None for result in results)
    assert sum(1 for r in results if r.success) == 1
    assert sum(
        1
        for r in results
        if r.status == "DUPLICATE_PUBLICATION"
    ) == 1
    assert publisher.calls == ["123"]
