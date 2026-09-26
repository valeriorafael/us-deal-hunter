from app.models.product import Product


def test_product_discount_vs_30d():
    product = Product(
        product_id="123",
        title="Test Product",
        current_price=75.0,
        average_price_30d=100.0,
    )

    assert product.discount_vs_30d == 0.25


def test_product_distance_from_90d_low():
    product = Product(
        product_id="123",
        title="Test Product",
        current_price=90.0,
        lowest_price_90d=75.0,
    )

    assert product.distance_from_90d_low == 0.20


def test_product_without_history():
    product = Product(
        product_id="123",
        title="Test Product",
        current_price=50.0,
    )

    assert product.discount_vs_30d is None
    assert product.distance_from_90d_low is None
