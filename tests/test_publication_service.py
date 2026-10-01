from datetime import datetime, timedelta

from app.models.deal import Deal
from app.models.product import Product
from app.publication.base import (
    DEFAULT_PUBLICATION_COOLDOWN,
    PublicationResult,
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
