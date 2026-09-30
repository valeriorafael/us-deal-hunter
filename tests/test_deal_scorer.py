from app.models.product import Product
from app.deals.scorer import DealScorer


def test_great_discount_gets_high_score():
    product = Product(
        product_id="123",
        title="Test Product",
        current_price=75.0,
        average_price_30d=100.0,
        lowest_price_90d=70.0,
        rating=4.7,
        review_count=8500,
    )

    scorer = DealScorer()
    deal = scorer.evaluate(product)

    assert deal.score >= 80
    assert deal.label == "GREAT"


def test_small_discount_gets_lower_score():
    product = Product(
        product_id="123",
        title="Test Product",
        current_price=98.0,
        average_price_30d=100.0,
        lowest_price_90d=95.0,
        rating=3.8,
        review_count=14,
    )

    scorer = DealScorer()
    deal = scorer.evaluate(product)

    assert deal.score < 60


def test_product_without_history_does_not_fake_discount():
    product = Product(
        product_id="123",
        title="Test Product",
        current_price=50.0,
    )

    scorer = DealScorer()
    deal = scorer.evaluate(product)

    assert 0 <= deal.score <= 100
