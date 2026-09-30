from app.models.product import Product
from app.deals.scorer import DealScorer


def test_no_history_has_low_confidence():
    product = Product(
        product_id="123",
        title="Unknown Product",
        current_price=100.0,
    )

    deal = DealScorer().evaluate(product)

    assert deal.confidence == "LOW"


def test_good_history_has_high_confidence():
    product = Product(
        product_id="123",
        title="Known Product",
        current_price=75.0,
        average_price_30d=100.0,
        lowest_price_90d=70.0,
        rating=4.7,
        review_count=8500,
    )

    deal = DealScorer().evaluate(product)

    assert deal.confidence == "HIGH"


def test_partial_history_has_medium_confidence():
    product = Product(
        product_id="123",
        title="Partial History Product",
        current_price=80.0,
        average_price_30d=100.0,
    )

    deal = DealScorer().evaluate(product)

    assert deal.confidence == "MEDIUM"
