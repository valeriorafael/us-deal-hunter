from app.models.product import Product
from app.deals.scorer import DealScorer


def test_no_history_is_low_confidence():
    product = Product(
        product_id="1",
        title="Unknown",
        current_price=100.0,
    )

    deal = DealScorer().evaluate(product)

    assert deal.confidence == "LOW"


def test_short_history_is_low_confidence():
    product = Product(
        product_id="1",
        title="Short History",
        current_price=80.0,
        average_price_30d=100.0,
        lowest_price_90d=70.0,
        price_history_days=3,
    )

    deal = DealScorer().evaluate(product)

    assert deal.confidence == "LOW"


def test_one_week_history_is_medium_confidence():
    product = Product(
        product_id="1",
        title="One Week",
        current_price=80.0,
        average_price_30d=100.0,
        lowest_price_90d=70.0,
        price_history_days=7,
    )

    deal = DealScorer().evaluate(product)

    assert deal.confidence == "MEDIUM"


def test_thirty_days_history_is_high_confidence():
    product = Product(
        product_id="1",
        title="One Month",
        current_price=80.0,
        average_price_30d=100.0,
        lowest_price_90d=70.0,
        price_history_days=30,
    )

    deal = DealScorer().evaluate(product)

    assert deal.confidence == "HIGH"


def test_ninety_days_history_is_high_confidence():
    product = Product(
        product_id="1",
        title="Three Months",
        current_price=80.0,
        average_price_30d=100.0,
        lowest_price_90d=70.0,
        price_history_days=90,
    )

    deal = DealScorer().evaluate(product)

    assert deal.confidence == "HIGH"
