from app.services.amazon_discovery import AmazonDiscovery


class FakeDiscoveryClient:
    def search_items(
        self,
        keywords,
        search_index,
        item_count,
        item_page,
        min_saving_percent,
    ):
        assert keywords == "gaming mouse"
        assert search_index == "Electronics"
        assert item_count == 2
        assert item_page == 1
        assert min_saving_percent == 20

        return {
            "searchResult": {
                "items": [
                    {
                        "asin": "B08N5WRWNW",
                        "detailPageURL": (
                            "https://www.amazon.com/dp/B08N5WRWNW"
                            "?tag=test-20&linkCode=ogi"
                        ),
                        "itemInfo": {
                            "title": {
                                "displayValue": "Gaming Mouse"
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
                    },
                    {
                        "asin": "B000000000",
                        "detailPageURL": (
                            "https://www.amazon.com/dp/B000000000"
                            "?tag=test-20&linkCode=ogi"
                        ),
                        "itemInfo": {
                            "title": {
                                "displayValue": "Keyboard"
                            }
                        },
                        "offersV2": {
                            "listings": [
                                {
                                    "price": {
                                        "amount": 50.0,
                                        "currency": "USD"
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }


def test_amazon_discovery_returns_products():
    products = AmazonDiscovery(
        client=FakeDiscoveryClient()
    ).discover(
        keywords="gaming mouse",
        search_index="Electronics",
        item_count=2,
        item_page=1,
        min_saving_percent=20,
    )

    assert len(products) == 2

    first = products[0]

    assert first.product_id == "B08N5WRWNW"
    assert first.title == "Gaming Mouse"
    assert first.current_price == 75.0
    assert first.currency == "USD"
    assert first.platform == "amazon"
    assert first.product_url == first.affiliate_url
    assert "tag=test-20" in first.affiliate_url


def test_amazon_discovery_returns_empty_when_search_fails():
    class EmptyClient:
        def search_items(
            self,
            keywords,
            search_index,
            item_count,
            item_page,
            min_saving_percent,
        ):
            return None

    products = AmazonDiscovery(
        client=EmptyClient()
    ).discover(
        keywords="gaming mouse",
    )

    assert products == []


def test_amazon_discovery_skips_invalid_items():
    class InvalidClient:
        def search_items(
            self,
            keywords,
            search_index,
            item_count,
            item_page,
            min_saving_percent,
        ):
            return {
                "searchResult": {
                    "items": [
                        {
                            "asin": "B08N5WRWNW",
                            "detailPageURL": (
                                "https://www.amazon.com/dp/"
                                "B08N5WRWNW?tag=test-20"
                            ),
                            "itemInfo": {
                                "title": {
                                    "displayValue": "Valid Product"
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
                        },
                        {
                            "asin": "INVALID"
                        }
                    ]
                }
            }

    products = AmazonDiscovery(
        client=InvalidClient()
    ).discover(
        keywords="gaming mouse",
    )

    assert len(products) == 1
    assert products[0].product_id == "B08N5WRWNW"
