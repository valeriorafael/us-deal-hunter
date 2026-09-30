from app.platforms.amazon_api import AmazonApiClient


def create_client():
    return AmazonApiClient(
        credential_id="test-id",
        credential_secret="test-secret",
        credential_version="3.1",
        partner_tag="test-20",
    )


def test_build_get_items_request():
    client = create_client()

    request = client.build_get_items_request(
        "B08N5WRWNW"
    )

    assert request["itemIds"] == ["B08N5WRWNW"]
    assert request["itemIdType"] == "ASIN"
    assert request["marketplace"] == "www.amazon.com"
    assert request["partnerTag"] == "test-20"


def test_get_items_requests_required_resources():
    client = create_client()

    request = client.build_get_items_request(
        "B08N5WRWNW"
    )

    resources = request["resources"]

    assert "itemInfo.title" in resources
    assert "offersV2.listings.price" in resources
    assert "images.primary.large" in resources


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_get_access_token_requests_oauth_token(monkeypatch):
    client = create_client()

    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))

        return FakeResponse({
            "access_token": "token-123",
            "expires_in": 3600,
        })

    monkeypatch.setattr(
        "app.platforms.amazon_api.requests.post",
        fake_post,
    )

    token = client.get_access_token()

    assert token == "token-123"
    assert len(calls) == 1

    url, kwargs = calls[0]

    assert url == client.TOKEN_URL

    assert kwargs["data"]["grant_type"] == "client_credentials"
    assert kwargs["data"]["client_id"] == "test-id"
    assert kwargs["data"]["client_secret"] == "test-secret"
    assert kwargs["data"]["version"] == "3.1"
    assert kwargs["data"]["scope"] == "creatorsapi::default"


def test_get_access_token_reuses_cached_token(monkeypatch):
    client = create_client()

    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)

        return FakeResponse({
            "access_token": "token-123",
            "expires_in": 3600,
        })

    monkeypatch.setattr(
        "app.platforms.amazon_api.requests.post",
        fake_post,
    )

    first = client.get_access_token()
    second = client.get_access_token()

    assert first == "token-123"
    assert second == "token-123"
    assert len(calls) == 1


def test_build_get_items_url():
    client = create_client()

    assert client.build_get_items_url() == (
        "https://creatorsapi.amazon/paapi5/getitems"
    )


def test_build_get_items_headers():
    client = create_client()

    headers = client.build_get_items_headers(
        "token-123"
    )

    assert headers["Authorization"] == "Bearer token-123"
    assert headers["Content-Type"] == "application/json"
    assert headers["x-amz-access-token"] == "token-123"
    assert "x-amz-date" in headers

def test_get_items_sends_expected_request(monkeypatch):
    client = create_client()

    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))

        return FakeResponse({
            "ItemsResult": {
                "Items": [
                    {
                        "ASIN": "B08N5WRWNW"
                    }
                ]
            }
        })

    monkeypatch.setattr(
        "app.platforms.amazon_api.requests.post",
        fake_post,
    )

    client._access_token = "token-123"
    client._token_expires_at = 9999999999

    result = client.get_items("B08N5WRWNW")

    assert result["ItemsResult"]["Items"][0]["ASIN"] == "B08N5WRWNW"

    assert len(calls) == 1

    url, kwargs = calls[0]

    assert url == client.build_get_items_url()

    assert kwargs["headers"]["Authorization"] == "Bearer token-123"
    assert kwargs["headers"]["x-amz-access-token"] == "token-123"

    assert kwargs["json"]["itemIds"] == ["B08N5WRWNW"]
    assert kwargs["json"]["itemIdType"] == "ASIN"
    assert kwargs["json"]["partnerTag"] == "test-20"
