from app.platforms.fake_amazon import FakeAmazonProvider


def test_get_existing_product():
    provider = FakeAmazonProvider()

    product = provider.get_product(
        "https://www.amazon.com/dp/B08N5WRWNW"
    )

    assert product is not None
    assert product.product_id == "B08N5WRWNW"
    assert product.title == "Test Product"
    assert product.current_price == 75.0
    assert product.platform == "amazon"


def test_get_unknown_product():
    provider = FakeAmazonProvider()

    product = provider.get_product(
        "https://www.amazon.com/dp/B000000000"
    )

    assert product is None


def test_get_invalid_url():
    provider = FakeAmazonProvider()

    product = provider.get_product(
        "https://example.com/product/123"
    )

    assert product is None
