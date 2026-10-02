from datetime import datetime, timedelta

from app.models.price_history import PriceHistory
from app.models.product import Product
from app.services.deal_pipeline import DealPipeline
from app.services.discovery_workflow import DiscoveryWorkflow
from app.services.price_history_repository import (
    PriceHistoryRepository,
)


class FakeDiscovery:
    def __init__(self, products):
        self.products = products
        self.calls = []

    def discover(
        self,
        keywords,
        search_index,
        item_count,
        item_page,
        min_saving_percent,
    ):
        self.calls.append(
            {
                "keywords": keywords,
                "search_index": search_index,
                "item_count": item_count,
                "item_page": item_page,
                "min_saving_percent": min_saving_percent,
            }
        )

        return self.products


def build_product(
    product_id,
    price,
):
    return Product(
        product_id=product_id,
        title=f"Product {product_id}",
        current_price=price,
        currency="USD",
        rating=4.7,
        review_count=8500,
        platform="amazon",
        affiliate_url=(
            f"https://www.amazon.com/dp/{product_id}"
            "?tag=test-20"
        ),
    )


def test_discovery_workflow_evaluates_discovered_products(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PriceHistoryRepository(
        str(tmp_path / "discovery.db")
    )

    repository.save(
        PriceHistory(
            "123",
            100.0,
            recorded_at=now - timedelta(days=60),
        )
    )
    repository.save(
        PriceHistory(
            "123",
            100.0,
            recorded_at=now - timedelta(days=20),
        )
    )
    repository.save(
        PriceHistory(
            "123",
            95.0,
            recorded_at=now - timedelta(days=10),
        )
    )
    repository.save(
        PriceHistory(
            "123",
            90.0,
            recorded_at=now - timedelta(days=5),
        )
    )

    discovery = FakeDiscovery(
        [
            build_product("123", 75.0),
        ]
    )

    workflow = DiscoveryWorkflow(
        discovery=discovery,
        pipeline=DealPipeline(
            repository=repository,
        ),
    )

    deals = workflow.discover_deals(
        keywords="gaming mouse",
        search_index="Electronics",
        item_count=10,
        item_page=1,
        min_saving_percent=20,
        now=now,
    )

    assert len(deals) == 1
    assert deals[0].product.product_id == "123"
    assert deals[0].score >= 60
    assert deals[0].confidence == "HIGH"

    assert discovery.calls == [
        {
            "keywords": "gaming mouse",
            "search_index": "Electronics",
            "item_count": 10,
            "item_page": 1,
            "min_saving_percent": 20,
        }
    ]


def test_discovery_workflow_returns_empty_when_no_deals(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PriceHistoryRepository(
        str(tmp_path / "empty.db")
    )

    discovery = FakeDiscovery(
        [
            build_product("123", 75.0),
        ]
    )

    workflow = DiscoveryWorkflow(
        discovery=discovery,
        pipeline=DealPipeline(
            repository=repository,
        ),
    )

    deals = workflow.discover_deals(
        keywords="gaming mouse",
        now=now,
    )

    assert deals == []


def test_discovery_workflow_deduplicates_products(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PriceHistoryRepository(
        str(tmp_path / "duplicates.db")
    )

    discovery = FakeDiscovery(
        [
            build_product("123", 75.0),
            build_product("123", 75.0),
        ]
    )

    workflow = DiscoveryWorkflow(
        discovery=discovery,
        pipeline=DealPipeline(
            repository=repository,
        ),
    )

    workflow.discover_deals(
        keywords="gaming mouse",
        now=now,
    )

    assert repository.count("123") == 1


def test_discovery_workflow_sorts_deals_by_score(
    tmp_path,
):
    now = datetime(2026, 8, 15, 12, 0)

    repository = PriceHistoryRepository(
        str(tmp_path / "sort.db")
    )

    for product_id, price in [
        ("123", 75.0),
        ("456", 85.0),
    ]:
        for days_ago, historical_price in [
            (60, 100.0),
            (20, 100.0),
            (10, 95.0),
            (5, 90.0),
        ]:
            repository.save(
                PriceHistory(
                    product_id,
                    historical_price,
                    recorded_at=now - timedelta(
                        days=days_ago
                    ),
                )
            )

    discovery = FakeDiscovery(
        [
            build_product("456", 85.0),
            build_product("123", 75.0),
        ]
    )

    workflow = DiscoveryWorkflow(
        discovery=discovery,
        pipeline=DealPipeline(
            repository=repository,
        ),
    )

    deals = workflow.discover_deals(
        keywords="gaming mouse",
        now=now,
    )

    assert len(deals) == 2
    assert deals[0].score >= deals[1].score
    assert deals[0].product.product_id == "123"


def test_discovery_workflow_survives_record_price_failure():
    now = datetime(2026, 8, 15, 12, 0)

    class FlakyPipeline:
        def __init__(self):
            self.recorded = []

        def record_price(self, product, now=None):
            if product.product_id == "BAD":
                raise ValueError("price parse failed")

            self.recorded.append(product.product_id)

        def evaluate(self, product, now=None):
            return None

    discovery = FakeDiscovery(
        [
            build_product("123", 75.0),
            build_product("BAD", 50.0),
            build_product("789", 30.0),
        ]
    )
    pipeline = FlakyPipeline()

    workflow = DiscoveryWorkflow(
        discovery=discovery,
        pipeline=pipeline,
    )

    deals = workflow.discover_deals(
        keywords="mouse",
        now=now,
    )

    assert deals == []
    assert pipeline.recorded == ["123", "789"]
    assert workflow.product_errors == [
        "product: BAD @ mouse: ValueError: price parse failed"
    ]


def test_discovery_workflow_survives_evaluate_failure():
    now = datetime(2026, 8, 15, 12, 0)

    class FlakyPipeline:
        def __init__(self):
            self.recorded = []

        def record_price(self, product, now=None):
            self.recorded.append(product.product_id)

        def evaluate(self, product, now=None):
            if product.product_id == "456":
                raise RuntimeError("bad history")

            return None

    discovery = FakeDiscovery(
        [
            build_product("123", 75.0),
            build_product("456", 50.0),
            build_product("789", 30.0),
        ]
    )
    pipeline = FlakyPipeline()

    workflow = DiscoveryWorkflow(
        discovery=discovery,
        pipeline=pipeline,
    )

    deals = workflow.discover_deals(
        keywords="mouse",
        now=now,
    )

    assert deals == []
    # all three were attempted, none aborted the loop
    assert pipeline.recorded == ["123", "456", "789"]
    assert workflow.product_errors == [
        "product: 456 @ mouse: RuntimeError: bad history"
    ]
