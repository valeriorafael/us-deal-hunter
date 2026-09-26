from app.platforms.amazon_parser import AmazonProductParser


def test_parser_builds_product_from_amazon_response():
    payload = {
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

    product = AmazonProductParser().parse(payload)

    assert product is not None
    assert product.product_id == "B08N5WRWNW"
    assert product.title == "Test Product"
    assert product.current_price == 75.0
    assert product.currency == "USD"
    assert product.platform == "amazon"


def test_parser_returns_none_when_no_items():
    payload = {
        "ItemsResult": {
            "Items": []
        }
    }

    product = AmazonProductParser().parse(payload)

    assert product is None
