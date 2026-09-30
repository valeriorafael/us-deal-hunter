import requests

from app.models.deal import Deal
from app.models.product import Product
from app.publication.formatter import DealMessageFormatter
from app.publication.telegram import TelegramPublisher


IMAGE_URL = (
    "https://images.example.com/test-product.jpg"
)


def build_deal(
    affiliate_url=(
        "https://www.amazon.com/dp/"
        "B08N5WRWNW?tag=test-20"
    ),
    image_url=IMAGE_URL,
):
    product = Product(
        product_id="B08N5WRWNW",
        title="Test Product",
        current_price=75.0,
        average_price_30d=100.0,
        lowest_price_90d=70.0,
        rating=4.7,
        review_count=8500,
        platform="amazon",
        affiliate_url=affiliate_url,
        image_url=image_url,
    )

    return Deal(
        product=product,
        score=88.0,
        label="GREAT",
        confidence="HIGH",
    )


def build_ok_response(message_id=789):
    class FakeResponse:
        def json(self):
            return {
                "ok": True,
                "result": {
                    "message_id": message_id
                },
            }

    return FakeResponse()


def build_api_error_response(description="Bad Request"):
    class FakeResponse:
        def json(self):
            return {
                "ok": False,
                "description": description,
            }

    return FakeResponse()


def build_invalid_json_response(status_code=200):
    class FakeResponse:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            raise ValueError("not json")

    return FakeResponse()


def build_recorder(outcomes):
    calls = []

    def fake_post(url, json, timeout):
        calls.append(
            {
                "url": url,
                "json": json,
                "timeout": timeout,
            }
        )

        outcome = outcomes[len(calls) - 1]

        if isinstance(outcome, Exception):
            raise outcome

        return outcome

    return calls, fake_post


def test_deal_message_formatter_contains_offer_data():
    message = DealMessageFormatter().format(
        build_deal()
    )

    assert "Test Product" in message
    assert "$75.00" in message
    assert "25%" in message
    assert "88/100" in message
    assert "VER OFERTA" in message
    assert "tag=test-20" in message


def test_telegram_publisher_sends_photo():
    captured = {}

    class FakeResponse:
        def json(self):
            return {
                "ok": True,
                "result": {
                    "message_id": 123
                },
            }

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal())

    assert result.success is True
    assert result.status == "PUBLISHED"
    assert result.message_id == 123

    assert captured["url"].endswith(
        "/bot123:test-token/sendPhoto"
    )

    assert captured["json"]["chat_id"] == "@testchannel"
    assert captured["json"]["photo"] == IMAGE_URL
    assert captured["json"]["parse_mode"] == "HTML"

    assert captured["json"]["reply_markup"] == {
        "inline_keyboard": [
            [
                {
                    "text": "🛒 VER OFERTA",
                    "url": (
                        "https://www.amazon.com/dp/"
                        "B08N5WRWNW?tag=test-20"
                    ),
                }
            ]
        ]
    }


def test_telegram_publisher_falls_back_to_text_without_image():
    captured = {}

    class FakeResponse:
        def json(self):
            return {
                "ok": True,
                "result": {
                    "message_id": 456
                },
            }

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(
        build_deal(image_url="")
    )

    assert result.success is True
    assert result.message_id == 456

    assert captured["url"].endswith(
        "/bot123:test-token/sendMessage"
    )

    assert "text" in captured["json"]
    assert "photo" not in captured["json"]
    assert captured["json"]["parse_mode"] == "HTML"
    assert "reply_markup" in captured["json"]


def test_telegram_publisher_rejects_missing_affiliate_link():
    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=lambda *args, **kwargs: None,
    )

    result = publisher.publish(
        build_deal(
            affiliate_url="",
        )
    )

    assert result.success is False
    assert result.status == "MISSING_AFFILIATE_LINK"


def test_returns_original_photo_error_when_fallback_also_fails():
    calls, fake_post = build_recorder(
        [
            build_api_error_response(
                "Bad Request: wrong file identifier"
            ),
            build_api_error_response(
                "Bad Request: chat not found"
            ),
        ]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@invalidchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal())

    assert len(calls) == 2
    assert calls[0]["url"].endswith("/sendPhoto")
    assert calls[1]["url"].endswith("/sendMessage")

    assert result.success is False
    assert result.status == "TELEGRAM_API_ERROR"
    assert result.reason == (
        "Bad Request: wrong file identifier"
    )


def test_does_not_retry_when_photo_succeeds():
    calls, fake_post = build_recorder(
        [build_ok_response(message_id=111)]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal())

    assert result.success is True
    assert result.message_id == 111

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/sendPhoto")
    assert "photo" in calls[0]["json"]
    assert "text" not in calls[0]["json"]


def test_sends_single_message_when_no_image():
    calls, fake_post = build_recorder(
        [build_ok_response(message_id=222)]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(
        build_deal(image_url="")
    )

    assert result.success is True
    assert result.message_id == 222

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/sendMessage")
    assert "text" in calls[0]["json"]
    assert "photo" not in calls[0]["json"]


def test_retries_as_text_when_photo_fails_with_api_error():
    calls, fake_post = build_recorder(
        [
            build_api_error_response(
                "Bad Request: wrong file identifier"
            ),
            build_ok_response(message_id=333),
        ]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal())

    assert result.success is True
    assert result.message_id == 333

    assert len(calls) == 2
    assert calls[0]["url"].endswith("/sendPhoto")
    assert calls[1]["url"].endswith("/sendMessage")

    assert "photo" in calls[0]["json"]
    assert "text" in calls[1]["json"]
    assert "photo" not in calls[1]["json"]


def test_retries_as_text_when_photo_fails_with_request_exception():
    calls, fake_post = build_recorder(
        [
            requests.RequestException("timed out"),
            build_ok_response(message_id=444),
        ]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal())

    assert result.success is True
    assert result.message_id == 444

    assert len(calls) == 2
    assert calls[0]["url"].endswith("/sendPhoto")
    assert calls[1]["url"].endswith("/sendMessage")
    assert "text" in calls[1]["json"]


def test_retries_as_text_when_photo_returns_invalid_json():
    calls, fake_post = build_recorder(
        [
            build_invalid_json_response(),
            build_ok_response(message_id=555),
        ]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal())

    assert result.success is True
    assert result.message_id == 555

    assert len(calls) == 2
    assert calls[0]["url"].endswith("/sendPhoto")
    assert calls[1]["url"].endswith("/sendMessage")


def test_fallback_preserves_caption_and_reply_markup():
    calls, fake_post = build_recorder(
        [
            build_api_error_response(),
            build_ok_response(message_id=666),
        ]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal())
    caption = DealMessageFormatter().format(build_deal())

    assert result.success is True

    photo_payload = calls[0]["json"]
    message_payload = calls[1]["json"]

    assert photo_payload["caption"] == caption
    assert message_payload["text"] == caption

    assert photo_payload["reply_markup"] == (
        message_payload["reply_markup"]
    )

    assert message_payload["parse_mode"] == "HTML"
    assert photo_payload["parse_mode"] == "HTML"

    assert message_payload["chat_id"] == "@testchannel"


def test_does_not_contact_telegram_when_affiliate_link_missing():
    calls, fake_post = build_recorder([])

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(
        build_deal(affiliate_url="")
    )

    assert result.success is False
    assert result.status == "MISSING_AFFILIATE_LINK"
    assert calls == []