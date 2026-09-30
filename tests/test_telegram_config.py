def test_telegram_config_from_environment(monkeypatch):
    from app.config import TelegramConfig

    monkeypatch.setenv(
        "TELEGRAM_BOT_TOKEN",
        "test-token",
    )
    monkeypatch.setenv(
        "TELEGRAM_CHAT_ID",
        "@testchannel",
    )

    config = TelegramConfig.from_environment()

    assert config.bot_token == "test-token"
    assert config.chat_id == "@testchannel"


def test_telegram_config_rejects_missing_chat_id(monkeypatch):
    from app.config import TelegramConfig

    monkeypatch.setenv(
        "TELEGRAM_BOT_TOKEN",
        "test-token",
    )
    monkeypatch.setenv(
        "TELEGRAM_CHAT_ID",
        "",
    )

    try:
        TelegramConfig.from_environment()
    except ValueError as exc:
        assert "TELEGRAM_CHAT_ID" in str(exc)
    else:
        raise AssertionError(
            "Missing Telegram chat id should raise ValueError"
        )


def test_telegram_config_creates_publisher(monkeypatch):
    from app.config import TelegramConfig
    from app.publication.telegram import TelegramPublisher

    monkeypatch.setenv(
        "TELEGRAM_BOT_TOKEN",
        "test-token",
    )
    monkeypatch.setenv(
        "TELEGRAM_CHAT_ID",
        "@testchannel",
    )

    config = TelegramConfig.from_environment()
    publisher = config.create_publisher()

    assert isinstance(publisher, TelegramPublisher)
    assert publisher.bot_token == "test-token"
    assert publisher.chat_id == "@testchannel"

