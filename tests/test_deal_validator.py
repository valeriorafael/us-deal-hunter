from app.models.product import Product
from app.deals.scorer import DealScorer
from app.deals.validator import DealValidator


def test_strong_deal_is_valid():
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
    result = DealValidator().validate(deal)

    assert result.is_valid is True
    assert result.status == "VALID"


def test_no_history_is_not_valid_deal():
    product = Product(
        product_id="123",
        title="Unknown Product",
        current_price=75.0,
    )

    deal = DealScorer().evaluate(product)
    result = DealValidator().validate(deal)

    assert result.is_valid is False
    assert result.status == "INSUFFICIENT_HISTORY"


def test_medium_confidence_is_uncertain():
    product = Product(
        product_id="123",
        title="Partial History Product",
        current_price=80.0,
        average_price_30d=100.0,
    )

    deal = DealScorer().evaluate(product)
    result = DealValidator().validate(deal)

    assert result.is_valid is False
    assert result.status == "UNCERTAIN"


def test_weak_deal_is_not_valid():
    product = Product(
        product_id="123",
        title="Weak Product",
        current_price=98.0,
        average_price_30d=100.0,
        lowest_price_90d=95.0,
        rating=3.8,
        review_count=14,
    )

    deal = DealScorer().evaluate(product)
    result = DealValidator().validate(deal)

    assert result.is_valid is False
    assert result.status == "LOW_SCORE"
