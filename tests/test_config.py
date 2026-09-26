from app.config import Settings


def test_settings_without_credentials_is_not_amazon_configured():
    settings = Settings()

    assert settings.amazon_configured is False


def test_settings_without_telegram_token_is_not_configured():
    settings = Settings()

    assert settings.telegram_configured is False
