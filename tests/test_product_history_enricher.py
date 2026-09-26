from datetime import datetime, timedelta

from app.models.product import Product
from app.models.price_history import PriceHistory
from app.services.product_history_enricher import ProductHistoryEnricher


def test_enricher_fills_product_history():
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
            recorded_at=now - timedelta(days=20),
        ),
        PriceHistory(
            "123",
            80.0,
            recorded_at=now - timedelta(days=10),
        ),
        PriceHistory(
            "123",
            70.0,
            recorded_at=now,
        ),
    ]

    enricher = ProductHistoryEnricher()

    enriched = enricher.enrich(
        product,
        history,
        now=now,
    )

    assert enriched.average_price_30d == 250 / 3
    assert enriched.lowest_price_90d == 70.0
    assert enriched.price_history_days == 20


def test_enricher_ignores_other_products():
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

    enriched = ProductHistoryEnricher().enrich(
        product,
        history,
        now=now,
    )

    assert enriched.average_price_30d == 100.0
    assert enriched.lowest_price_90d == 100.0


def test_enricher_handles_empty_history():
    product = Product(
        product_id="123",
        title="Unknown Product",
        current_price=50.0,
    )

    enriched = ProductHistoryEnricher().enrich(
        product,
        [],
    )

    assert enriched.average_price_30d is None
    assert enriched.lowest_price_90d is None
    assert enriched.price_history_days == 0
