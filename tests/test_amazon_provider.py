from app.platforms.amazon_provider import AmazonProvider


class FakeClient:
    def get_items(self, asin):
        assert asin == "B08N5WRWNW"

        return {
            "ItemsResult": {
                "Items": [
                    {
                        "ASIN": "B08N5WRWNW",
                        "DetailPageURL": (
                            "https://www.amazon.com/dp/B08N5WRWNW"
                            "?tag=testtag-20&linkCode=ogi"
                        ),
                        "ItemInfo": {
                            "Title": {
                                "DisplayValue": "Test Product"
                            }
                        },
                        "Offers": {
                            "Listings": [
                                {
                                    "Price": {
                                        "Amount": 75.0,
                                        "Currency": "USD"
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }


def test_amazon_provider_returns_product():
    provider = AmazonProvider(client=FakeClient())

    original_url = "https://www.amazon.com/dp/B08N5WRWNW"

    product = provider.get_product(original_url)

    assert product is not None
    assert product.product_id == "B08N5WRWNW"
    assert product.title == "Test Product"
    assert product.current_price == 75.0
    assert product.currency == "USD"
    assert product.platform == "amazon"
    assert product.product_url == original_url
    assert product.affiliate_url == (
        "https://www.amazon.com/dp/B08N5WRWNW"
        "?tag=testtag-20&linkCode=ogi"
    )


def test_amazon_provider_rejects_invalid_url():
    provider = AmazonProvider(client=FakeClient())

    product = provider.get_product(
        "https://example.com/product/123"
    )

    assert product is None


def test_amazon_provider_returns_none_when_api_has_no_items():
    class EmptyClient:
        def get_items(self, asin):
            return {
                "ItemsResult": {
                    "Items": []
                }
            }

    provider = AmazonProvider(client=EmptyClient())

    product = provider.get_product(
        "https://www.amazon.com/dp/B08N5WRWNW"
    )

    assert product is None


def test_amazon_provider_returns_none_when_price_is_missing():
    class NoPriceClient:
        def get_items(self, asin):
            return {
                "ItemsResult": {
                    "Items": [
                        {
                            "ASIN": "B08N5WRWNW",
                            "ItemInfo": {
                                "Title": {
                                    "DisplayValue": "Test Product"
                                }
                            },
                            "Offers": {
                                "Listings": []
                            }
                        }
                    ]
                }
            }

    provider = AmazonProvider(client=NoPriceClient())

    product = provider.get_product(
        "https://www.amazon.com/dp/B08N5WRWNW"
    )

    assert product is None

def test_amazon_provider_supports_current_creators_api_structure():
    class CurrentSdkClient:
        def get_items(self, asin):
            assert asin == "B08N5WRWNW"

            return {
                "itemsResult": {
                    "items": [
                        {
                            "asin": "B08N5WRWNW",
                            "detailPageURL": (
                                "https://www.amazon.com/dp/B08N5WRWNW"
                                "?tag=testtag-20&linkCode=ogi"
                            ),
                            "itemInfo": {
                                "title": {
                                    "displayValue": "Current SDK Product"
                                }
                            },
                            "offersV2": {
                                "listings": [
                                    {
                                        "price": {
                                            "amount": 75.0,
                                            "currency": "USD"
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            }

    provider = AmazonProvider(client=CurrentSdkClient())

    product = provider.get_product(
        "https://www.amazon.com/dp/B08N5WRWNW"
    )

    assert product is not None
    assert product.product_id == "B08N5WRWNW"
    assert product.title == "Current SDK Product"
    assert product.current_price == 75.0
    assert product.currency == "USD"
    assert product.product_url == (
        "https://www.amazon.com/dp/B08N5WRWNW"
    )
    assert product.affiliate_url == (
        "https://www.amazon.com/dp/B08N5WRWNW"
        "?tag=testtag-20&linkCode=ogi"
    )
