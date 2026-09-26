from app.models.product import Product
from app.models.deal import Deal


def test_deal_uses_product_price_metrics():
    product = Product(
        product_id="123",
        title="Test Product",
        current_price=75.0,
        average_price_30d=100.0,
        lowest_price_90d=70.0,
    )

    deal = Deal(product=product)

    assert deal.discount_vs_30d == 0.25
    assert deal.distance_from_90d_low == 5 / 70


def test_deal_is_not_a_deal_by_default():
    product = Product(
        product_id="123",
        title="Test Product",
        current_price=100.0,
    )

    deal = Deal(product=product)

    assert deal.score == 0.0
    assert deal.is_deal is False


def test_deal_can_be_marked_as_good_deal():
    product = Product(
        product_id="123",
        title="Test Product",
        current_price=75.0,
    )

    deal = Deal(
        product=product,
        score=80.0,
        label="GREAT",
        reasons=("20% below average price",),
    )

    assert deal.score == 80.0
    assert deal.label == "GREAT"
    assert deal.is_deal is True
    assert "20% below average price" in deal.reasons
