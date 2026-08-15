from app.deals.scorer import DealScorer
from app.models.product import Product


def test_excellent_deal_gets_high_score():
    product = Product(
        product_id="TEST001",
        title="Sony WH-1000XM5",
        current_price=249.0,
        average_price_30d=299.0,
        lowest_price_90d=229.0,
        rating=4.7,
        review_count=32000,
    )

    result = DealScorer().score(product)

    assert 85 <= result.score <= 100
    assert result.price_score == 32.0
    assert result.history_score == 14.0
    assert result.is_deal is True


def test_bad_deal_gets_low_score():
    product = Product(
        product_id="TEST002",
        title="Generic Headphones",
        current_price=99.0,
        average_price_30d=100.0,
        lowest_price_90d=80.0,
        rating=3.5,
        review_count=50,
    )

    result = DealScorer().score(product)

    assert result.score < 70
    assert result.is_deal is False


def test_missing_history_reduces_confidence():
    product = Product(
        product_id="TEST003",
        title="New Product",
        current_price=50.0,
        rating=4.8,
        review_count=1000,
    )

    result = DealScorer().score(product)

    assert result.score < 85
    assert result.is_deal is False


def test_score_is_always_between_zero_and_hundred():
    product = Product(
        product_id="TEST004",
        title="Test Product",
        current_price=1.0,
        average_price_30d=1000.0,
        lowest_price_90d=1.0,
        rating=5.0,
        review_count=100000,
    )

    result = DealScorer().score(product)

    assert 0 <= result.score <= 100

