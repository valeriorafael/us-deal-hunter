from datetime import datetime

from app.models.deal import Deal
from app.models.product import Product
from app.publication.base import PublicationResult
from app.services.hunt_workflow import HuntWorkflow


def build_deal(product_id):
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
        score=88.0,
        label="GREAT",
        confidence="HIGH",
    )


def test_hunt_workflow_publishes_discovered_deals():
    now = datetime(2026, 8, 15, 12, 0)
    captured = []

    class FakeDiscoveryWorkflow:
        def discover_deals(
            self,
            keywords,
            search_index,
            item_count,
            item_page,
            min_saving_percent,
            now,
        ):
            assert keywords == "gaming mouse"
            assert search_index == "Electronics"
            assert item_count == 10
            assert item_page == 1
            assert min_saving_percent == 20
            assert now == datetime(2026, 8, 15, 12, 0)

            return [
                build_deal("123"),
                build_deal("456"),
            ]

    class FakePublicationService:
        def publish(self, deal, now=None):
            captured.append(
                (deal.product.product_id, now)
            )

            return PublicationResult(
                success=True,
                status="PUBLISHED",
                reason="Published.",
                message_id=len(captured),
            )

    workflow = HuntWorkflow(
        discovery_workflow=FakeDiscoveryWorkflow(),
        publication_service=FakePublicationService(),
    )

    result = workflow.discover_and_publish(
        keywords="gaming mouse",
        search_index="Electronics",
        item_count=10,
        item_page=1,
        min_saving_percent=20,
        now=now,
    )

    assert result.discovered_count == 2
    assert result.published_count == 2
    assert len(result.results) == 2
    assert all(
        item[1] == now
        for item in captured
    )


def test_hunt_workflow_counts_only_successful_publications():
    class FakeDiscoveryWorkflow:
        def discover_deals(
            self,
            keywords,
            search_index,
            item_count,
            item_page,
            min_saving_percent,
            now,
        ):
            return [
                build_deal("123"),
                build_deal("456"),
                build_deal("789"),
            ]

    calls = 0

    class FakePublicationService:
        def publish(self, deal, now=None):
            nonlocal calls
            calls += 1

            if deal.product.product_id == "456":
                return PublicationResult(
                    success=False,
                    status="DUPLICATE_PUBLICATION",
                    reason="Product was published recently.",
                )

            return PublicationResult(
                success=True,
                status="PUBLISHED",
                reason="Published.",
                message_id=calls,
            )

    workflow = HuntWorkflow(
        discovery_workflow=FakeDiscoveryWorkflow(),
        publication_service=FakePublicationService(),
    )

    result = workflow.discover_and_publish(
        keywords="gaming mouse",
    )

    assert result.discovered_count == 3
    assert result.published_count == 2
    assert len(result.results) == 3
    assert result.results[1].status == "DUPLICATE_PUBLICATION"


def test_hunt_workflow_handles_no_deals():
    class FakeDiscoveryWorkflow:
        def discover_deals(
            self,
            keywords,
            search_index,
            item_count,
            item_page,
            min_saving_percent,
            now,
        ):
            return []

    class FakePublicationService:
        def publish(self, deal, now=None):
            raise AssertionError(
                "Publisher should not be called."
            )

    workflow = HuntWorkflow(
        discovery_workflow=FakeDiscoveryWorkflow(),
        publication_service=FakePublicationService(),
    )

    result = workflow.discover_and_publish(
        keywords="nothing",
    )

    assert result.discovered_count == 0
    assert result.published_count == 0
    assert result.results == ()

def test_hunt_workflow_stops_after_publication_limit():
    from app.services.hunt_policy import HuntPublicationPolicy

    calls = []

    class FakeDiscoveryWorkflow:
        def discover_deals(
            self,
            keywords,
            search_index,
            item_count,
            item_page,
            min_saving_percent,
            now,
        ):
            return [
                build_deal("123"),
                build_deal("456"),
                build_deal("789"),
                build_deal("999"),
            ]

    class FakePublicationService:
        def publish(self, deal, now=None):
            calls.append(deal.product.product_id)

            return PublicationResult(
                success=True,
                status="PUBLISHED",
                reason="Published.",
                message_id=len(calls),
            )

    workflow = HuntWorkflow(
        discovery_workflow=FakeDiscoveryWorkflow(),
        publication_service=FakePublicationService(),
        policy=HuntPublicationPolicy(
            max_publications_per_run=3
        ),
    )

    result = workflow.discover_and_publish(
        keywords="gaming",
    )

    assert result.discovered_count == 4
    assert result.published_count == 3
    assert len(result.results) == 3
    assert calls == [
        "123",
        "456",
        "789",
    ]


def test_hunt_workflow_duplicates_do_not_consume_publication_limit():
    from app.services.hunt_policy import HuntPublicationPolicy

    calls = []

    class FakeDiscoveryWorkflow:
        def discover_deals(
            self,
            keywords,
            search_index,
            item_count,
            item_page,
            min_saving_percent,
            now,
        ):
            return [
                build_deal("123"),
                build_deal("456"),
                build_deal("789"),
            ]

    class FakePublicationService:
        def publish(self, deal, now=None):
            calls.append(deal.product.product_id)

            if deal.product.product_id == "123":
                return PublicationResult(
                    success=False,
                    status="DUPLICATE_PUBLICATION",
                    reason="Product was published recently.",
                )

            return PublicationResult(
                success=True,
                status="PUBLISHED",
                reason="Published.",
                message_id=len(calls),
            )

    workflow = HuntWorkflow(
        discovery_workflow=FakeDiscoveryWorkflow(),
        publication_service=FakePublicationService(),
        policy=HuntPublicationPolicy(
            max_publications_per_run=2
        ),
    )

    result = workflow.discover_and_publish(
        keywords="gaming",
    )

    assert result.discovered_count == 3
    assert result.published_count == 2
    assert len(result.results) == 3
    assert calls == [
        "123",
        "456",
        "789",
    ]

def test_hunt_workflow_can_publish_an_existing_deal_list():
    from app.services.hunt_policy import HuntPublicationPolicy

    calls = []

    class FakeDiscoveryWorkflow:
        def discover_deals(self, **kwargs):
            return []

    class FakePublicationService:
        def publish(self, deal, now=None):
            calls.append(deal.product.product_id)

            return PublicationResult(
                success=True,
                status="PUBLISHED",
                reason="Published.",
                message_id=len(calls),
            )

    workflow = HuntWorkflow(
        discovery_workflow=FakeDiscoveryWorkflow(),
        publication_service=FakePublicationService(),
        policy=HuntPublicationPolicy(
            max_publications_per_run=2
        ),
    )

    result = workflow.publish_deals(
        [
            build_deal("123"),
            build_deal("456"),
            build_deal("789"),
        ]
    )

    assert result.discovered_count == 3
    assert result.published_count == 2
    assert len(result.results) == 2
    assert calls == ["123", "456"]


def test_hunt_workflow_publication_limit_counts_only_successes():
    from app.services.hunt_policy import HuntPublicationPolicy

    calls = []

    class FakeDiscoveryWorkflow:
        def discover_deals(self, **kwargs):
            return []

    class FakePublicationService:
        def publish(self, deal, now=None):
            calls.append(deal.product.product_id)

            if deal.product.product_id == "123":
                return PublicationResult(
                    success=False,
                    status="DUPLICATE_PUBLICATION",
                    reason="Already published.",
                )

            return PublicationResult(
                success=True,
                status="PUBLISHED",
                reason="Published.",
                message_id=len(calls),
            )

    workflow = HuntWorkflow(
        discovery_workflow=FakeDiscoveryWorkflow(),
        publication_service=FakePublicationService(),
        policy=HuntPublicationPolicy(
            max_publications_per_run=2
        ),
    )

    result = workflow.publish_deals(
        [
            build_deal("123"),
            build_deal("456"),
            build_deal("789"),
        ]
    )

    assert result.discovered_count == 3
    assert result.published_count == 2
    assert len(result.results) == 3
    assert calls == ["123", "456", "789"]
