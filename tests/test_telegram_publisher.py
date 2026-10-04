import pytest

import requests

from app.models.deal import Deal
from app.models.product import Product
from app.publication.formatter import (
    MAX_TITLE_LENGTH,
    DealMessageFormatter,
)
from app.publication.telegram import (
    MAX_CAPTION_LENGTH,
    MAX_MESSAGE_LENGTH,
    PHOTO_FALLBACK_STATUSES,
    TelegramPublisher,
    fit_message,
)


IMAGE_URL = (
    "https://images.example.com/test-product.jpg"
)


def build_deal(
    affiliate_url=(
        "https://www.amazon.com/dp/"
        "B08N5WRWNW?tag=test-20"
    ),
    image_url=IMAGE_URL,
    title="Test Product",
):
    product = Product(
        product_id="B08N5WRWNW",
        title=title,
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


def build_api_error_response(
    description="Bad Request",
    error_code=None,
    retry_after=None,
):
    class FakeResponse:
        def json(self):
            payload = {
                "ok": False,
                "description": description,
            }

            if error_code is not None:
                payload["error_code"] = error_code

            if retry_after is not None:
                payload["parameters"] = {
                    "retry_after": retry_after
                }

            return payload

    return FakeResponse()


def build_rate_limit_response(retry_after=None):
    return build_api_error_response(
        "Too Many Requests: retry after 3",
        error_code=429,
        retry_after=retry_after,
    )


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
    assert "VIEW DEAL" in message
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
                    "text": "🛒 VIEW DEAL",
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


def test_photo_request_exception_does_not_fallback():
    """A-2/H2: an unknown photo outcome must not be retried as a
    second message, so only one HTTP call is made."""
    calls, fake_post = build_recorder(
        [requests.RequestException("timed out")]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal())

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/sendPhoto")
    assert result.success is False
    assert result.status == "TELEGRAM_REQUEST_ERROR"
    assert result.indeterminate is True


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

def test_request_error_marks_result_indeterminate():
    calls, fake_post = build_recorder(
        [requests.RequestException("timed out")]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal(image_url=None))

    assert result.success is False
    assert result.status == "TELEGRAM_REQUEST_ERROR"
    assert result.indeterminate is True
    assert len(calls) == 1


def test_api_error_stays_deterministic():
    calls, fake_post = build_recorder(
        [build_api_error_response("chat not found")]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal(image_url=None))

    assert result.success is False
    assert result.status == "TELEGRAM_API_ERROR"
    assert result.indeterminate is False
    assert len(calls) == 1


def test_fallback_marks_indeterminate_when_text_unknown():
    """Deterministic photo failure frees the text fallback; if the
    fallback outcome is unknown the combined result is unknown
    while the photo error stays the root cause."""
    calls, fake_post = build_recorder(
        [
            build_api_error_response(
                "Bad Request: wrong file identifier"
            ),
            requests.RequestException("timed out"),
        ]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal())

    assert len(calls) == 2
    assert calls[0]["url"].endswith("/sendPhoto")
    assert calls[1]["url"].endswith("/sendMessage")
    assert result.success is False
    assert result.status == "TELEGRAM_API_ERROR"
    assert result.indeterminate is True


def test_both_definitive_failures_stay_deterministic():
    calls, fake_post = build_recorder(
        [
            build_api_error_response("wrong file identifier"),
            build_api_error_response("chat not found"),
        ]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal())

    assert result.success is False
    assert result.status == "TELEGRAM_API_ERROR"
    assert result.indeterminate is False
    assert result.reason == "wrong file identifier"
    assert len(calls) == 2


def _build_publisher(outcomes, **kwargs):
    calls, fake_post = build_recorder(outcomes)
    sleeps = []

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
        sleep=sleeps.append,
        rng=lambda: 1.0,
        **kwargs,
    )

    return publisher, calls, sleeps


def test_photo_retry_sleeps_exact_retry_after_and_succeeds():
    publisher, calls, sleeps = _build_publisher(
        [
            build_rate_limit_response(retry_after=1),
            build_ok_response(message_id=555),
        ]
    )

    result = publisher.publish(build_deal())

    assert result.success is True
    assert result.message_id == 555
    assert len(calls) == 2
    assert all(
        call["url"].endswith("/sendPhoto") for call in calls
    )
    assert sleeps == [1.0]


def test_rate_limited_photo_is_not_retried_as_text():
    publisher, calls, sleeps = _build_publisher(
        [build_rate_limit_response(retry_after=60)]
    )

    result = publisher.publish(build_deal())

    assert sleeps == []
    assert len(calls) == 1
    assert calls[0]["url"].endswith("/sendPhoto")
    assert result.success is False
    assert result.status == "TELEGRAM_RATE_LIMITED"
    assert result.indeterminate is False


def test_http_5xx_json_retries_with_full_jitter_then_gives_up():
    publisher, calls, sleeps = _build_publisher(
        [
            build_api_error_response(
                "Internal Server Error",
                error_code=503,
            ),
            build_api_error_response(
                "Internal Server Error",
                error_code=503,
            ),
            build_api_error_response(
                "Internal Server Error",
                error_code=503,
            ),
        ]
    )

    result = publisher.publish(build_deal(image_url=None))

    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]
    assert result.success is False
    assert result.status == "TELEGRAM_API_ERROR"
    assert result.indeterminate is False


def test_rate_limit_gives_up_after_three_calls():
    publisher, calls, sleeps = _build_publisher(
        [
            build_rate_limit_response(retry_after=1),
            build_rate_limit_response(retry_after=1),
            build_rate_limit_response(retry_after=1),
        ]
    )

    result = publisher.publish(build_deal(image_url=None))

    assert len(calls) == 3
    assert sleeps == [1.0, 1.0]
    assert result.success is False
    assert result.status == "TELEGRAM_RATE_LIMITED"


def test_retry_log_never_exposes_the_bot_token(caplog):
    import logging

    with caplog.at_level(
        logging.WARNING,
        logger="app.publication.telegram",
    ):
        publisher, calls, sleeps = _build_publisher(
            [
                build_api_error_response(
                    "Internal Server Error",
                    error_code=503,
                ),
                build_ok_response(message_id=777),
            ]
        )

        result = publisher.publish(build_deal(image_url=None))

    assert result.success is True
    assert len(calls) == 2
    assert sleeps == [0.5]
    assert (
        "telegram retry attempt=1/3 "
        "delay=0.50s status=TELEGRAM_API_ERROR"
    ) in caplog.text
    assert "123:test-token" not in caplog.text
    assert "api.telegram.org" not in caplog.text


def test_invalid_json_is_not_retried():
    publisher, calls, sleeps = _build_publisher(
        [build_invalid_json_response()]
    )

    result = publisher.publish(build_deal(image_url=None))

    assert len(calls) == 1
    assert sleeps == []
    assert result.success is False
    assert result.status == "TELEGRAM_INVALID_RESPONSE"
    assert result.indeterminate is False


def test_http_5xx_without_json_is_unknown_and_not_retried():
    publisher, calls, sleeps = _build_publisher(
        [build_invalid_json_response(status_code=500)]
    )

    result = publisher.publish(build_deal(image_url=None))

    assert len(calls) == 1
    assert sleeps == []
    assert result.success is False
    assert result.status == "TELEGRAM_HTTP_ERROR"
    assert result.indeterminate is True


def test_request_error_reason_never_exposes_secrets():
    token = "123456:AAHz7Kd9xL2mNpQr4sTvWxYzAbCdEf"
    bare = "987654:BBBBBBBBBBBBBBBBBBBBBBBBBB"

    publisher, calls, sleeps = _build_publisher(
        [
            requests.RequestException(
                "Max retries exceeded with url: "
                f"/bot{token}/sendPhoto "
                f"token=abc123 fallback {bare}"
            )
        ]
    )

    result = publisher.publish(build_deal(image_url=None))

    assert result.success is False
    assert result.status == "TELEGRAM_REQUEST_ERROR"
    assert result.indeterminate is True
    assert token not in result.reason
    assert "abc123" not in result.reason
    assert bare not in result.reason
    assert "/bot[REDACTED]/" in result.reason
    assert "token=[REDACTED]" in result.reason


def test_fit_message_leaves_short_text_unchanged():
    text = "<b>Deal</b>\n👉 VIEW DEAL"

    assert fit_message(text, 100) == text


def test_fit_message_keeps_footer_and_respects_limit():
    footer = (
        '👉 <a href="https://www.amazon.com/dp/'
        'B1?tag=t-20">VIEW DEAL</a>'
    )
    text = f"<b>{'A' * 500}</b>\n{footer}"
    limit = 400

    fitted = fit_message(text, limit)

    assert len(fitted) <= limit
    assert fitted.endswith(footer)
    assert "<b>" not in fitted
    assert "A" * 500 not in fitted


def test_fit_message_handles_single_line_text():
    text = f"<b>{'A' * 300}</b>"

    fitted = fit_message(text, 100)

    assert len(fitted) <= 100
    assert set(fitted) == {"A"}


def test_fit_message_falls_back_when_footer_exceeds_limit():
    text = "X" * 50 + "\n" + "Y" * 200

    fitted = fit_message(text, 50)

    assert len(fitted) <= 50
    assert fitted == "X" * 50


def test_formatter_truncates_very_long_title():
    message = DealMessageFormatter().format(
        build_deal(title="T" * 500)
    )

    assert "T" * MAX_TITLE_LENGTH in message
    assert "T" * (MAX_TITLE_LENGTH + 1) not in message


def _huge_formatter():
    class HugeFormatter:
        def format(self, deal):
            return (
                "🔥 <b>DEAL</b>\n" * 500
                + '👉 <a href="https://example.com/x">'
                "VIEW DEAL</a>"
            )

    return HugeFormatter()


def test_photo_caption_never_exceeds_the_caption_limit():
    calls, fake_post = build_recorder(
        [build_ok_response(message_id=1)]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
        formatter=_huge_formatter(),
    )

    result = publisher.publish(build_deal())

    caption = calls[0]["json"]["caption"]

    assert result.success is True
    assert len(caption) <= MAX_CAPTION_LENGTH
    assert caption.endswith(
        '👉 <a href="https://example.com/x">VIEW DEAL</a>'
    )


def test_text_message_never_exceeds_the_message_limit():
    calls, fake_post = build_recorder(
        [build_ok_response(message_id=2)]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
        formatter=_huge_formatter(),
    )

    result = publisher.publish(build_deal(image_url=None))

    text = calls[0]["json"]["text"]

    assert result.success is True
    assert len(text) <= MAX_MESSAGE_LENGTH
    assert text.endswith(
        '👉 <a href="https://example.com/x">VIEW DEAL</a>'
    )


def test_retry_after_at_max_is_honoured_exactly():
    publisher, calls, sleeps = _build_publisher(
        [
            build_rate_limit_response(retry_after=10.0),
            build_rate_limit_response(retry_after=10.0),
            build_rate_limit_response(retry_after=10.0),
        ]
    )

    result = publisher.publish(build_deal(image_url=None))

    assert len(calls) == 3
    assert sleeps == [10.0, 10.0]
    assert result.success is False
    assert result.status == "TELEGRAM_RATE_LIMITED"


def test_retry_after_above_max_gives_up_without_sleeping():
    publisher, calls, sleeps = _build_publisher(
        [build_rate_limit_response(retry_after=10.001)]
    )

    result = publisher.publish(build_deal(image_url=None))

    assert len(calls) == 1
    assert sleeps == []
    assert result.success is False
    assert result.status == "TELEGRAM_RATE_LIMITED"
    assert result.indeterminate is False


def test_http_400_json_error_is_not_retried():
    publisher, calls, sleeps = _build_publisher(
        [
            build_api_error_response(
                "Bad Request: chat not found",
                error_code=400,
            )
        ]
    )

    result = publisher.publish(build_deal(image_url=None))

    assert len(calls) == 1
    assert sleeps == []
    assert result.success is False
    assert result.status == "TELEGRAM_API_ERROR"
    assert result.indeterminate is False


def test_formatter_message_is_english():
    deal = Deal(
        product=build_deal().product,
        score=88.0,
        label="GREAT",
        confidence="HIGH",
        reference_price=100.0,
    )

    message = DealMessageFormatter().format(deal)

    assert "DEAL FOUND" in message
    assert "Was: <s>$100.00</s>" in message
    assert "below the 30-day average" in message
    assert "Lowest price in 90d: $70.00" in message
    assert "(8,500 reviews)" in message
    assert "VIEW DEAL" in message

    assert "OFERTA ENCONTRADA" not in message
    assert "avalia" not in message
    assert "abaixo" not in message
    assert "Menor pre\u00e7o" not in message
    assert "VER OFERTA" not in message


def test_formatter_uses_english_verified_deal_when_there_is_no_score():
    deal = Deal(
        product=build_deal().product,
        score=0.0,
        label="CURATED",
        confidence="VERIFIED",
    )

    message = DealMessageFormatter().format(deal)

    assert "Verified deal" in message
    assert "Oferta verificada" not in message


def test_reply_markup_button_is_english():
    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=None,
    )

    markup = publisher._reply_markup("https://example.com/x")

    assert markup["inline_keyboard"][0][0]["text"] == (
        "\U0001f6d2 VIEW DEAL"
    )


@pytest.mark.parametrize(
    "image_url",
    [
        None,
        "",
        "   ",
        "not-a-url",
        "/local/path.jpg",
        "ftp://example.com/x.jpg",
        "javascript:alert(1)",
        "http://",
        123,
    ],
)
def test_unusable_image_url_goes_straight_to_send_message(
    image_url,
):
    calls, fake_post = build_recorder([build_ok_response()])

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal(image_url=image_url))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/sendMessage")
    assert result.success is True
    assert "photo" not in calls[0]["json"]
    assert "text" in calls[0]["json"]


def test_usable_image_url_is_sent_as_photo_in_a_single_call():
    calls, fake_post = build_recorder([build_ok_response()])

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal(image_url=IMAGE_URL))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/sendPhoto")
    assert calls[0]["json"]["photo"] == IMAGE_URL
    assert result.success is True


def test_unknown_photo_outcome_does_not_fall_back_to_text():
    calls, fake_post = build_recorder(
        [build_invalid_json_response(status_code=500)]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(build_deal())

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/sendPhoto")
    assert result.success is False
    assert result.indeterminate is True


def test_fallback_only_allows_modelled_telegram_outcomes():
    assert "TELEGRAM_RATE_LIMITED" not in PHOTO_FALLBACK_STATUSES
    assert "TELEGRAM_REQUEST_ERROR" not in PHOTO_FALLBACK_STATUSES
    assert "PUBLISHED" not in PHOTO_FALLBACK_STATUSES


def test_curated_file_publishes_as_photo_with_english_text(
    monkeypatch,
):
    from app.services.curated_deals import CuratedDealLoader

    class ExplodingResolver:
        def resolve(self, source_url, fallback_urls=None):
            raise AssertionError(
                "data/curated_deals.json must already carry "
                "a usable image_url."
            )

    monkeypatch.setenv(
        "AMAZON_PARTNER_TAG",
        "dealhunter0e2-20",
    )

    config = CuratedDealLoader(
        image_resolver=ExplodingResolver()
    ).load("data/curated_deals.json")

    assert len(config.deals) == 2

    deal = config.deals[0]

    calls, fake_post = build_recorder(
        [build_ok_response(message_id=4242)]
    )

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    result = publisher.publish(deal)

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/sendPhoto")
    assert calls[0]["json"]["photo"] == deal.product.image_url

    caption = calls[0]["json"]["caption"]
    assert caption.startswith("\U0001f525 <b>DEAL FOUND</b>")
    assert "VIEW DEAL" in caption
    assert "VER OFERTA" not in caption
    assert "OFERTA ENCONTRADA" not in caption
    assert "tag=dealhunter0e2-20" in caption
    assert "Source: Slickdeals" in caption

    assert result.success is True
    assert result.message_id == 4242
