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


def build_credentialed_client(**kwargs):
    return AmazonApiClient(
        access_key="test-id",
        secret_key="test-secret",
        partner_tag="test-20",
        credential_version="3.1",
        **kwargs,
    )


def patch_instant_retry(monkeypatch):
    from app.services.resilience import RetryPolicy

    monkeypatch.setattr(
        "app.platforms.amazon_client.AMAZON_RETRY_POLICY",
        RetryPolicy(
            attempts=3,
            base_delay=0.0,
            multiplier=2.0,
            max_delay=0.0,
        ),
    )


def test_search_items_retries_transient_failures(monkeypatch):
    patch_instant_retry(monkeypatch)

    calls = {"count": 0}

    class FakeApi:
        def search_items(
            self,
            x_marketplace,
            search_items_request_content,
        ):
            calls["count"] += 1

            if calls["count"] < 3:
                raise ConnectionError("connection reset")

            return {"searchResult": {"items": []}}

    client = build_credentialed_client()
    client._api = FakeApi()

    result = client.search_items(keywords="gaming mouse")

    assert result == {"searchResult": {"items": []}}
    assert calls["count"] == 3


def test_search_items_gives_up_after_policy_attempts(
    monkeypatch,
):
    patch_instant_retry(monkeypatch)

    calls = {"count": 0}

    class FakeApi:
        def search_items(
            self,
            x_marketplace,
            search_items_request_content,
        ):
            calls["count"] += 1
            raise ConnectionError("still down")

    client = build_credentialed_client()
    client._api = FakeApi()

    with pytest.raises(ConnectionError):
        client.search_items(keywords="gaming mouse")

    assert calls["count"] == 3


def test_search_items_does_not_retry_non_transient(monkeypatch):
    patch_instant_retry(monkeypatch)

    calls = {"count": 0}

    class FakeApi:
        def search_items(
            self,
            x_marketplace,
            search_items_request_content,
        ):
            calls["count"] += 1
            raise ValueError("malformed response")

    client = build_credentialed_client()
    client._api = FakeApi()

    with pytest.raises(ValueError):
        client.search_items(keywords="gaming mouse")

    assert calls["count"] == 1


def test_get_items_is_never_retried():
    calls = {"count": 0}

    class FakeApi:
        def get_items(
            self,
            x_marketplace,
            get_items_request_content,
        ):
            calls["count"] += 1
            raise ConnectionError("connection reset")

    client = build_credentialed_client()
    client._api = FakeApi()

    with pytest.raises(ConnectionError):
        client.get_items("B08N5WRWNW")

    assert calls["count"] == 1
