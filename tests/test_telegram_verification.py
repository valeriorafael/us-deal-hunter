"""Channel verification probe (phase 4, item 6 / decisions A-4, A-5)."""

import requests

from app.publication.base import Verdict
from app.publication.telegram import TelegramPublisher


AFFILIATE_URL = (
    "https://www.amazon.com/dp/B08N5WRWNW?tag=test-20"
)


def build_ok_response():
    class FakeResponse:
        def json(self):
            return {"ok": True, "result": True}

    return FakeResponse()


def build_api_error_response(
    description="Bad Request",
    error_code=400,
):
    class FakeResponse:
        def json(self):
            return {
                "ok": False,
                "error_code": error_code,
                "description": description,
            }

    return FakeResponse()


def build_invalid_json_response():
    class FakeResponse:
        status_code = 200

        def json(self):
            raise ValueError("not json")

    return FakeResponse()


def build_probe(outcomes):
    calls = []

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json})
        outcome = outcomes[len(calls) - 1]

        if isinstance(outcome, Exception):
            raise outcome

        return outcome

    publisher = TelegramPublisher(
        bot_token="123:test-token",
        chat_id="@testchannel",
        post=fake_post,
    )

    return publisher, calls


def verify(publisher, message_id=42):
    return publisher.verify_message(
        message_id,
        affiliate_url=AFFILIATE_URL,
    )


def test_probe_returns_exists_when_telegram_confirms():
    publisher, calls = build_probe([build_ok_response()])

    verdict = verify(publisher)

    assert verdict is Verdict.EXISTS
    assert len(calls) == 1
    assert calls[0]["url"].endswith(
        "/bot123:test-token/editMessageReplyMarkup"
    )


def test_probe_returns_absent_only_for_explicit_not_found():
    publisher, _ = build_probe(
        [
            build_api_error_response(
                "Bad Request: message to edit not found"
            )
        ]
    )

    assert verify(publisher) is Verdict.ABSENT


def test_probe_accepts_delete_not_found_phrase():
    publisher, _ = build_probe(
        [
            build_api_error_response(
                "Bad Request: message to delete not found"
            )
        ]
    )

    assert verify(publisher) is Verdict.ABSENT


def test_probe_treats_not_modified_as_exists():
    publisher, _ = build_probe(
        [
            build_api_error_response(
                "Bad Request: message is not modified"
            )
        ]
    )

    assert verify(publisher) is Verdict.EXISTS


def test_probe_returns_unknown_for_other_client_errors():
    publisher, _ = build_probe(
        [build_api_error_response("Bad Request: chat not found")]
    )

    assert verify(publisher) is Verdict.UNKNOWN


def test_probe_returns_unknown_for_rate_limit_errors():
    publisher, _ = build_probe(
        [
            build_api_error_response(
                "Too Many Requests: retry after 3",
                error_code=429,
            )
        ]
    )

    assert verify(publisher) is Verdict.UNKNOWN


def test_probe_returns_unknown_on_network_failure():
    publisher, _ = build_probe(
        [requests.RequestException("timed out")]
    )

    assert verify(publisher) is Verdict.UNKNOWN


def test_probe_returns_unknown_on_invalid_json():
    publisher, _ = build_probe([build_invalid_json_response()])

    assert verify(publisher) is Verdict.UNKNOWN


def test_probe_sends_the_identical_reply_markup():
    publisher, calls = build_probe([build_ok_response()])

    verify(publisher, message_id=42)

    payload = calls[0]["json"]

    assert payload["chat_id"] == "@testchannel"
    assert payload["message_id"] == 42
    assert payload["reply_markup"] == {
        "inline_keyboard": [
            [
                {
                    "text": "🛒 VER OFERTA",
                    "url": AFFILIATE_URL,
                }
            ]
        ]
    }


def test_probe_returns_unknown_for_unauthorized():
    publisher, _ = build_probe(
        [
            build_api_error_response(
                "Unauthorized",
                error_code=401,
            )
        ]
    )

    assert verify(publisher) is Verdict.UNKNOWN
