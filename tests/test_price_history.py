from datetime import datetime

import pytest

from app.models.price_history import PriceHistory


def test_price_history_stores_price_observation():
    recorded_at = datetime(2026, 8, 15, 12, 0, 0)

    history = PriceHistory(
        product_id="123",
        price=79.90,
        recorded_at=recorded_at,
    )

    assert history.product_id == "123"
    assert history.price == 79.90
    assert history.currency == "USD"
    assert history.recorded_at == recorded_at


def test_price_history_creates_timestamp_when_missing():
    history = PriceHistory(
        product_id="123",
        price=79.90,
    )

    assert history.recorded_at is not None
    assert isinstance(history.recorded_at, datetime)


def test_price_history_rejects_empty_product_id():
    with pytest.raises(ValueError):
        PriceHistory(
            product_id="",
            price=79.90,
        )


def test_price_history_rejects_zero_price():
    with pytest.raises(ValueError):
        PriceHistory(
            product_id="123",
            price=0,
        )


def test_price_history_rejects_negative_price():
    with pytest.raises(ValueError):
        PriceHistory(
            product_id="123",
            price=-10,
        )


def test_price_history_is_immutable():
    history = PriceHistory(
        product_id="123",
        price=79.90,
    )

    with pytest.raises(Exception):
        history.price = 50.0
