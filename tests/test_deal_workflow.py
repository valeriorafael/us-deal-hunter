from datetime import datetime

from app.models.deal import Deal
from app.models.product import Product
from app.publication.base import PublicationResult
from app.services.deal_workflow import DealWorkflow


def build_deal():
    return Deal(
        product=Product(
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
        ),
        score=88.0,
        label="GREAT",
        confidence="HIGH",
    )


def test_workflow_analyzes_deal():
    now = datetime(2026, 8, 15, 12, 0)

    class FakeHunter:
        def analyze(self, url, now=None):
            assert url == "https://example.com/product"
            assert now == datetime(2026, 8, 15, 12, 0)
            return build_deal()

    class FakePublicationService:
        def publish(self, deal, now=None):
            raise AssertionError(
                "Publication should not run."
            )

    workflow = DealWorkflow(
        hunter=FakeHunter(),
        publication_service=FakePublicationService(),
    )

    deal = workflow.analyze(
        "https://example.com/product",
        now=now,
    )

    assert deal is not None
    assert deal.product.product_id == "123"


def test_workflow_returns_no_deal_result():
    class FakeHunter:
        def analyze(self, url, now=None):
            return None

    class FakePublicationService:
        def publish(self, deal, now=None):
            raise AssertionError(
                "Publication should not run."
            )

    workflow = DealWorkflow(
        hunter=FakeHunter(),
        publication_service=FakePublicationService(),
    )

    result = workflow.analyze_and_publish(
        "https://example.com/product"
    )

    assert result.success is False
    assert result.status == "NO_DEAL"


def test_workflow_analyzes_and_publishes_deal():
    now = datetime(2026, 8, 15, 12, 0)
    captured = {}

    class FakeHunter:
        def analyze(self, url, now=None):
            captured["url"] = url
            captured["now"] = now
            return build_deal()

    class FakePublicationService:
        def publish(self, deal, now=None):
            captured["deal"] = deal
            captured["publish_now"] = now

            return PublicationResult(
                success=True,
                status="PUBLISHED",
                reason="Published.",
                message_id=123,
            )

    workflow = DealWorkflow(
        hunter=FakeHunter(),
        publication_service=FakePublicationService(),
    )

    result = workflow.analyze_and_publish(
        "https://example.com/product",
        now=now,
    )

    assert result.success is True
    assert result.status == "PUBLISHED"
    assert result.message_id == 123
    assert captured["url"] == "https://example.com/product"
    assert captured["now"] == now
    assert captured["deal"].product.product_id == "123"
    assert captured["publish_now"] == now
