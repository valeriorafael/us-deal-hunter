from datetime import datetime, timedelta

from app.deals.hunter import DealHunter
from app.platforms.fake_amazon import FakeAmazonProvider
from app.platforms.registry import ProviderRegistry
from app.services.deal_pipeline import DealPipeline
from app.services.price_history_repository import PriceHistoryRepository
from app.models.price_history import PriceHistory


def create_hunter(tmp_path):
    repository = PriceHistoryRepository(
        str(tmp_path / "hunter.db")
    )

    now = datetime(2026, 8, 15)

    repository.save(
        PriceHistory(
            "B08N5WRWNW",
            70.0,
            recorded_at=now - timedelta(days=60),
        )
    )

    repository.save(
        PriceHistory(
            "B08N5WRWNW",
            100.0,
            recorded_at=now - timedelta(days=30),
        )
    )

    repository.save(
        PriceHistory(
            "B08N5WRWNW",
            100.0,
            recorded_at=now - timedelta(days=20),
        )
    )

    repository.save(
        PriceHistory(
            "B08N5WRWNW",
            100.0,
            recorded_at=now - timedelta(days=10),
        )
    )

    pipeline = DealPipeline(
        repository=repository,
    )

    registry = ProviderRegistry(
        providers={
            "amazon": FakeAmazonProvider(),
        }
    )

    return DealHunter(
        registry=registry,
        pipeline=pipeline,
    )


def test_hunter_finds_great_deal(tmp_path):
    hunter = create_hunter(tmp_path)

    deal = hunter.analyze(
        "https://www.amazon.com/dp/B08N5WRWNW",
        now=datetime(2026, 8, 15),
    )

    assert deal is not None
    assert deal.product.product_id == "B08N5WRWNW"
    assert deal.score >= 80
    assert deal.label == "GREAT"


def test_hunter_returns_none_for_unknown_product(tmp_path):
    hunter = create_hunter(tmp_path)

    deal = hunter.analyze(
        "https://www.amazon.com/dp/B000000000"
    )

    assert deal is None


def test_hunter_returns_none_for_invalid_url(tmp_path):
    hunter = create_hunter(tmp_path)

    deal = hunter.analyze(
        "https://example.com/product/123"
    )

    assert deal is None

def test_hunter_records_price_through_pipeline(tmp_path):
    from app.services.deal_pipeline import DealPipeline
    from app.services.price_history_repository import PriceHistoryRepository

    repository = PriceHistoryRepository(
        str(tmp_path / "hunter_pipeline.db")
    )

    pipeline = DealPipeline(
        repository=repository,
    )

    registry = ProviderRegistry(
        providers={
            "amazon": FakeAmazonProvider(),
        }
    )

    hunter = DealHunter(
        registry=registry,
        pipeline=pipeline,
    )

    deal = hunter.analyze(
        "https://www.amazon.com/dp/B08N5WRWNW"
    )

    assert deal is None

    history = repository.get_by_product(
        "B08N5WRWNW"
    )

    assert len(history) == 1
    assert history[0].price == 75.0


def test_hunter_records_price_before_pipeline_evaluation(tmp_path):
    from app.platforms.amazon_provider import AmazonProvider
    from app.services.deal_pipeline import DealPipeline
    from app.services.price_history_repository import PriceHistoryRepository

    repository = PriceHistoryRepository(
        str(tmp_path / "hunter_real_flow.db")
    )

    pipeline = DealPipeline(
        repository=repository,
    )

    provider = AmazonProvider(
        client=FakeAmazonClientForHunter(),
    )

    registry = ProviderRegistry(
        providers={
            "amazon": provider,
        }
    )

    hunter = DealHunter(
        registry=registry,
        pipeline=pipeline,
    )

    hunter.analyze(
        "https://www.amazon.com/dp/B08N5WRWNW"
    )

    history = repository.get_by_product(
        "B08N5WRWNW"
    )

    assert len(history) == 1
    assert history[0].price == 75.0


class FakeAmazonClientForHunter:
    def get_items(self, asin):
        assert asin == "B08N5WRWNW"

        return {
            "ItemsResult": {
                "Items": [
                    {
                        "ASIN": "B08N5WRWNW",
                        "ItemInfo": {
                            "Title": {
                                "DisplayValue": "Test Product"
                            }
                        },
                        "Offers": {
                            "Listings": [
                                {
                                    "Price": {
                                        "Amount": 75.0,
                                        "Currency": "USD"
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }


def test_hunter_integrates_amazon_provider_with_pipeline(tmp_path):
    from app.platforms.amazon_provider import AmazonProvider
    from app.services.deal_pipeline import DealPipeline
    from app.services.price_history_repository import PriceHistoryRepository

    repository = PriceHistoryRepository(
        str(tmp_path / "hunter_integration.db")
    )

    pipeline = DealPipeline(
        repository=repository,
    )

    provider = AmazonProvider(
        client=FakeAmazonClientForHunter(),
    )

    registry = ProviderRegistry(
        providers={
            "amazon": provider,
        }
    )

    hunter = DealHunter(
        registry=registry,
        pipeline=pipeline,
    )

    deal = hunter.analyze(
        "https://www.amazon.com/dp/B08N5WRWNW"
    )

    assert deal is None

    history = repository.get_by_product(
        "B08N5WRWNW"
    )

    assert len(history) == 1
    assert history[0].price == 75.0
    assert history[0].currency == "USD"


def test_hunter_uses_price_history_to_evaluate_second_collection(tmp_path):
    from datetime import datetime, timedelta

    from app.models.price_history import PriceHistory
    from app.platforms.amazon_provider import AmazonProvider
    from app.services.deal_pipeline import DealPipeline
    from app.services.price_history_repository import PriceHistoryRepository

    now = datetime(2026, 8, 15)

    repository = PriceHistoryRepository(
        str(tmp_path / "hunter_history.db")
    )

    repository.save(
        PriceHistory(
            product_id="B08N5WRWNW",
            price=100.0,
            currency="USD",
            recorded_at=now - timedelta(days=30),
        )
    )

    repository.save(
        PriceHistory(
            product_id="B08N5WRWNW",
            price=95.0,
            currency="USD",
            recorded_at=now - timedelta(days=15),
        )
    )

    pipeline = DealPipeline(
        repository=repository,
    )

    provider = AmazonProvider(
        client=FakeAmazonClientForHunter(),
    )

    registry = ProviderRegistry(
        providers={
            "amazon": provider,
        }
    )

    hunter = DealHunter(
        registry=registry,
        pipeline=pipeline,
    )

    deal = hunter.analyze(
        "https://www.amazon.com/dp/B08N5WRWNW",
        now=now,
    )

    assert deal is not None
    assert deal.confidence == "HIGH"
    assert deal.product.current_price == 75.0


def test_hunter_uses_distributed_price_history(tmp_path):
    from datetime import datetime, timedelta

    from app.models.price_history import PriceHistory
    from app.platforms.amazon_provider import AmazonProvider
    from app.services.deal_pipeline import DealPipeline
    from app.services.price_history_repository import PriceHistoryRepository

    now = datetime(2026, 8, 15)

    repository = PriceHistoryRepository(
        str(tmp_path / "hunter_distributed_history.db")
    )

    for days_ago, price in [
        (45, 100.0),
        (30, 105.0),
        (15, 98.0),
    ]:
        repository.save(
            PriceHistory(
                product_id="B08N5WRWNW",
                price=price,
                currency="USD",
                recorded_at=now - timedelta(days=days_ago),
            )
        )

    pipeline = DealPipeline(
        repository=repository,
    )

    provider = AmazonProvider(
        client=FakeAmazonClientForHunter(),
    )

    registry = ProviderRegistry(
        providers={
            "amazon": provider,
        }
    )

    hunter = DealHunter(
        registry=registry,
        pipeline=pipeline,
    )

    deal = hunter.analyze(
        "https://www.amazon.com/dp/B08N5WRWNW",
        now=now,
    )

    assert deal is not None
    assert deal.confidence == "HIGH"
    assert deal.product.current_price == 75.0
    assert deal.score >= 60

    history = repository.get_by_product(
        "B08N5WRWNW"
    )

    assert len(history) == 4
