def test_amazon_client_from_environment(monkeypatch):
    from app.config import AmazonConfig

    monkeypatch.setenv(
        "AMAZON_CREDENTIAL_ID",
        "test-id",
    )
    monkeypatch.setenv(
        "AMAZON_CREDENTIAL_SECRET",
        "test-secret",
    )
    monkeypatch.setenv(
        "AMAZON_CREDENTIAL_VERSION",
        "3.1",
    )
    monkeypatch.setenv(
        "AMAZON_PARTNER_TAG",
        "test-20",
    )

    config = AmazonConfig.from_environment()

    assert config.credential_id == "test-id"
    assert config.credential_secret == "test-secret"
    assert config.credential_version == "3.1"
    assert config.partner_tag == "test-20"


def test_amazon_config_rejects_missing_credentials(monkeypatch):
    from app.config import AmazonConfig

    monkeypatch.delenv("AMAZON_CREDENTIAL_ID", raising=False)
    monkeypatch.delenv("AMAZON_CREDENTIAL_SECRET", raising=False)
    monkeypatch.delenv("AMAZON_CREDENTIAL_VERSION", raising=False)
    monkeypatch.delenv("AMAZON_PARTNER_TAG", raising=False)

    try:
        AmazonConfig.from_environment()
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Missing Amazon credentials should raise ValueError"
        )


def test_amazon_config_builds_current_api_client(monkeypatch):
    from app.config import AmazonConfig
    from app.platforms.amazon_client import AmazonApiClient

    monkeypatch.setenv("AMAZON_CREDENTIAL_ID", "test-id")
    monkeypatch.setenv("AMAZON_CREDENTIAL_SECRET", "test-secret")
    monkeypatch.setenv("AMAZON_CREDENTIAL_VERSION", "3.1")
    monkeypatch.setenv("AMAZON_PARTNER_TAG", "test-20")

    config = AmazonConfig.from_environment()
    client = config.create_client()

    assert isinstance(client, AmazonApiClient)
    assert client.access_key == "test-id"
    assert client.secret_key == "test-secret"
    assert client.credential_version == "3.1"
    assert client.partner_tag == "test-20"
