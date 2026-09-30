from datetime import datetime

from app.models.deal import Deal
from app.models.product import Product
from app.publication.base import PublicationResult
from app.publication.service import PublicationService
from app.services.publication_repository import (
    PublicationRepository,
)


def build_valid_deal():
    product = Product(
        product_id="123",
        title="Test Product",
        current_price=75.0,
        average_price_30d=100.0,
        lowest_price_90d=70.0,
        rating=4.7,
        review_count=8500,
        platform="amazon",
        affiliate_url=(
            "https://www.amazon.com/dp/123?tag=test-20"
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
