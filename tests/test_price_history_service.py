from datetime import datetime, timedelta

from app.models.price_history import PriceHistory
from app.services.price_history import PriceHistoryService


def test_service_calculates_30_day_average():
    now = datetime(2026, 8, 15)

    history = [
        PriceHistory("123", 100.0, recorded_at=now - timedelta(days=10)),
        PriceHistory("123", 80.0, recorded_at=now - timedelta(days=5)),
        PriceHistory("123", 60.0, recorded_at=now),
    ]

    service = PriceHistoryService(history)

    assert service.average_price(days=30, now=now) == 80.0


def test_service_finds_90_day_low():
    now = datetime(2026, 8, 15)

    history = [
        PriceHistory("123", 100.0, recorded_at=now - timedelta(days=80)),
        PriceHistory("123", 75.0, recorded_at=now - timedelta(days=30)),
        PriceHistory("123", 90.0, recorded_at=now),
    ]

    service = PriceHistoryService(history)

    assert service.lowest_price(days=90, now=now) == 75.0


def test_old_price_is_ignored():
    now = datetime(2026, 8, 15)

    history = [
        PriceHistory("123", 20.0, recorded_at=now - timedelta(days=100)),
        PriceHistory("123", 80.0, recorded_at=now - timedelta(days=10)),
    ]

    service = PriceHistoryService(history)

    assert service.lowest_price(days=90, now=now) == 80.0


def test_service_counts_history_days():
    now = datetime(2026, 8, 15)

    history = [
        PriceHistory("123", 100.0, recorded_at=now - timedelta(days=20)),
        PriceHistory("123", 90.0, recorded_at=now - timedelta(days=10)),
        PriceHistory("123", 80.0, recorded_at=now),
    ]

    service = PriceHistoryService(history)

    assert service.history_days(now=now) == 20


def test_empty_history_returns_none():
    service = PriceHistoryService([])

    assert service.average_price(days=30) is None
    assert service.lowest_price(days=90) is None
    assert service.history_days() == 0


def test_service_ignores_other_products():
    now = datetime(2026, 8, 15)

    history = [
        PriceHistory("123", 100.0, recorded_at=now),
        PriceHistory("999", 10.0, recorded_at=now),
    ]

    service = PriceHistoryService(history, product_id="123")

    assert service.lowest_price(days=90, now=now) == 100.0
