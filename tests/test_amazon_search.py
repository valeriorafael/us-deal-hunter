from app.platforms.amazon_client import AmazonApiClient


def test_search_items_requires_credentials():
    client = AmazonApiClient()

    result = client.search_items(
        keywords="gaming mouse",
    )

    assert result is None


def test_search_items_builds_request():
    captured = {}

    class FakeApi:
        def search_items(
            self,
            x_marketplace,
            search_items_request_content,
        ):
            captured["marketplace"] = x_marketplace
            captured["request"] = search_items_request_content

            return {
                "searchResult": {
                    "items": []
                }
            }

    client = AmazonApiClient(
        access_key="test-id",
        secret_key="test-secret",
        partner_tag="test-20",
        credential_version="3.1",
    )

    client._api = FakeApi()

    result = client.search_items(
        keywords="gaming mouse",
        search_index="Electronics",
        item_count=5,
        item_page=2,
        min_saving_percent=20,
    )

    request = captured["request"]

    assert result == {
        "searchResult": {
            "items": []
        }
    }
    assert captured["marketplace"] == "www.amazon.com"
    assert request.keywords == "gaming mouse"
    assert request.search_index == "Electronics"
    assert request.item_count == 5
    assert request.item_page == 2
    assert request.min_saving_percent == 20
    assert request.partner_tag == "test-20"


def test_search_items_returns_sdk_dict():
    class FakeResponse:
        def to_dict(self):
            return {
                "searchResult": {
                    "items": [
                        {
                            "asin": "B08N5WRWNW"
                        }
                    ]
                }
            }

    class FakeApi:
        def search_items(
            self,
            x_marketplace,
            search_items_request_content,
        ):
            return FakeResponse()

    client = AmazonApiClient(
        access_key="test-id",
        secret_key="test-secret",
        partner_tag="test-20",
        credential_version="3.1",
    )

    client._api = FakeApi()

    result = client.search_items(
        keywords="gaming mouse",
    )

    assert result["searchResult"]["items"][0]["asin"] == (
        "B08N5WRWNW"
    )
