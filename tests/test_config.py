from app.config import Settings


def test_settings_without_credentials_is_not_amazon_configured():
    settings = Settings()

    assert settings.amazon_configured is False


def test_settings_without_telegram_configuration_is_not_configured(
    monkeypatch,
):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    settings = Settings()

    assert settings.telegram_configured is False


def test_settings_with_telegram_token_but_without_chat_id_is_not_configured(
    monkeypatch,
):
    monkeypatch.setenv(
        "TELEGRAM_BOT_TOKEN",
        "test-token",
    )
    monkeypatch.delenv(
        "TELEGRAM_CHAT_ID",
        raising=False,
    )

    settings = Settings()

    assert settings.telegram_configured is False


def test_settings_with_complete_telegram_configuration_is_configured(
    monkeypatch,
):
    monkeypatch.setenv(
        "TELEGRAM_BOT_TOKEN",
        "test-token",
    )
    monkeypatch.setenv(
        "TELEGRAM_CHAT_ID",
        "@testchannel",
    )

    settings = Settings()

    assert settings.telegram_configured is True
