from datetime import datetime, timedelta

from app.models.product import Product
from app.models.price_history import PriceHistory
from app.services.deal_pipeline import DealPipeline
import pytest


def test_pipeline_evaluates_product_with_strong_history():
    now = datetime(2026, 8, 15)

    product = Product(
        product_id="123",
        title="Test Product",
        current_price=75.0,
        rating=4.7,
        review_count=8500,
    )

    history = [
        PriceHistory(
            "123",
            100.0,
            recorded_at=now - timedelta(days=90),
        ),
        PriceHistory(
            "123",
            95.0,
            recorded_at=now - timedelta(days=60),
        ),
        PriceHistory(
            "123",
            100.0,
            recorded_at=now - timedelta(days=20),
        ),
        PriceHistory(
            "123",
            95.0,
            recorded_at=now - timedelta(days=10),
        ),
        PriceHistory(
            "123",
            70.0,
            recorded_at=now,
        ),
    ]

    pipeline = DealPipeline()

    deal = pipeline.evaluate(
        product,
        history,
        now=now,
    )

    assert deal is not None
    assert deal.product.product_id == "123"
    assert deal.product.average_price_30d == 88.33333333333333
    assert deal.product.lowest_price_90d == 70.0
    assert deal.product.price_history_days == 90
    assert deal.score >= 80
    assert deal.label == "GREAT"
    assert deal.confidence == "HIGH"


def test_pipeline_ignores_history_from_other_products():
    now = datetime(2026, 8, 15)

    product = Product(
        product_id="123",
        title="Test Product",
        current_price=75.0,
    )

    history = [
        PriceHistory(
            "123",
            100.0,
            recorded_at=now,
        ),
        PriceHistory(
            "999",
            10.0,
            recorded_at=now,
        ),
    ]

    deal = DealPipeline().evaluate(
        product,
        history,
        now=now,
    )

    # Only one historical observation means confidence is MEDIUM,
    # therefore the validator correctly rejects the deal.
    assert deal is None


def test_pipeline_rejects_insufficient_history():
    now = datetime(2026, 8, 15)

    product = Product(
        product_id="123",
        title="Unknown Product",
        current_price=100.0,
    )

    deal = DealPipeline().evaluate(
        product,
        [],
        now=now,
    )

    assert deal is None


def test_pipeline_can_use_persisted_history(tmp_path):
    from app.services.price_history_repository import PriceHistoryRepository

    now = datetime(2026, 8, 15)

    repository = PriceHistoryRepository(str(tmp_path / "test.db"))

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
            95.0,
            recorded_at=now - timedelta(days=30),
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
            70.0,
            recorded_at=now,
        )
    )

    product = Product(
        product_id="123",
        title="Test Product",
        current_price=75.0,
        rating=4.7,
        review_count=8500,
    )

    pipeline = DealPipeline(repository=repository)

    deal = pipeline.evaluate(
        product,
        now=now,
    )

    assert deal is not None
    assert deal.product.product_id == "123"
    assert deal.confidence == "HIGH"


def test_pipeline_records_current_price_before_evaluation(tmp_path):
    from app.services.price_history_repository import PriceHistoryRepository

    now = datetime(2026, 8, 15)

    repository = PriceHistoryRepository(
        str(tmp_path / "pipeline.db")
    )

    product = Product(
        product_id="123",
        title="Test Product",
        current_price=75.0,
        rating=4.7,
        review_count=8500,
    )

    pipeline = DealPipeline(repository=repository)

    pipeline.record_price(
        product,
        now=now,
    )

    history = repository.get_by_product("123")

    assert len(history) == 1
    assert history[0].product_id == "123"
    assert history[0].price == 75.0
    assert history[0].recorded_at == now
