import pytest

from app.platforms.amazon_client import AmazonApiClient


def test_amazon_client_can_be_created_without_credentials():
    client = AmazonApiClient()

    assert client.access_key is None
    assert client.secret_key is None
    assert client.partner_tag is None
    assert client.marketplace == "www.amazon.com"


def test_amazon_client_requires_api_implementation():
    client = AmazonApiClient()

    with pytest.raises(NotImplementedError):
        client.get_item("B08N5WRWNW")
