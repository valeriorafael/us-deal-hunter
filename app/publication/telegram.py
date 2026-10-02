"""Telegram publisher with retry, limits and channel verification.

Phase 4 (spec 17):
1. retry with exponential backoff + jitter (3 total attempts);
2. ``retry_after`` respected, never sleeping more than
   ``RETRY_AFTER_MAX`` seconds;
3. caption/text limits enforced before sending;
4. every reason string is sanitized before it leaves this module;
5. PENDING/SENDING ownership stays with PublicationService;
6. ``verify_message`` lets the service reconcile unknown rows.
"""

import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import requests

from app.deals.affiliate_validator import AffiliateLinkValidator
from app.models.deal import Deal
from app.publication.base import (
    STATUS_PUBLISHED,
    STATUS_TELEGRAM_API_ERROR,
    STATUS_TELEGRAM_HTTP_ERROR,
    STATUS_TELEGRAM_INVALID_RESPONSE,
    STATUS_TELEGRAM_RATE_LIMITED,
    STATUS_TELEGRAM_REQUEST_ERROR,
    PublicationResult,
    Publisher,
    Verdict,
)
from app.publication.formatter import DealMessageFormatter
from app.services.resilience import (
    RetryPolicy,
    compute_backoff,
)
from app.services.run_summary import sanitize_text

logger = logging.getLogger(__name__)

# Telegram hard limits (phase 4, item 3).
MAX_CAPTION_LENGTH = 1024
MAX_MESSAGE_LENGTH = 4096

# Phase 4, items 1 and 2: attempts is the TOTAL number of HTTP
# calls (spec 9.5 minimum of 3), delays are full-jittered and
# capped; retry_after is honoured only up to RETRY_AFTER_MAX.
TELEGRAM_RETRY_ATTEMPTS = 3
TELEGRAM_RETRY_BASE_DELAY = 0.5
TELEGRAM_RETRY_MULTIPLIER = 2.0
TELEGRAM_RETRY_MAX_DELAY = 5.0
RETRY_AFTER_MAX = 10.0

TELEGRAM_RETRY_POLICY = RetryPolicy(
    attempts=TELEGRAM_RETRY_ATTEMPTS,
    base_delay=TELEGRAM_RETRY_BASE_DELAY,
    multiplier=TELEGRAM_RETRY_MULTIPLIER,
    max_delay=TELEGRAM_RETRY_MAX_DELAY,
)

_COMPLETE_TAG = re.compile(r"<[^<>]*>")
_UNTERMINATED_TAG = re.compile(r"<[^<>]*$")
_TRAILING_ENTITY = re.compile(r"&[A-Za-z0-9#]*$")


def _strip_html_tags(text: str) -> str:
    """Remove closed tags and any tag cut off mid-way."""
    without_closed = _COMPLETE_TAG.sub("", text)

    return _UNTERMINATED_TAG.sub("", without_closed)


def _trim_entity_tail(text: str) -> str:
    """Drop a trailing HTML entity fragment left by truncation.

    ``&amp;`` survives (it ends in ``;``), ``&amp`` does not.
    """
    return _TRAILING_ENTITY.sub("", text)


def fit_message(text: str, limit: int) -> str:
    """Shorten ``text`` to at most ``limit`` characters.

    The last line holds the affiliate link and is preserved
    whenever it can fit; the body above it is cut and reduced to
    plain text so no HTML entity or tag can be left unbalanced.
    """
    if len(text) <= limit:
        return text

    if "\n" not in text:
        return _trim_entity_tail(_strip_html_tags(text[:limit]))

    head, footer = text.rsplit("\n", 1)
    budget = limit - len(footer) - 1

    if budget <= 0:
        return _trim_entity_tail(_strip_html_tags(text[:limit]))

    head = _strip_html_tags(head)
    head = _trim_entity_tail(head[:budget]).rstrip()

    fitted = f"{head}\n{footer}"

    if len(fitted) > limit:
        return _trim_entity_tail(_strip_html_tags(text[:limit]))

    return fitted


@dataclass(frozen=True)
class _SendOutcome:
    """One HTTP attempt, plus what the retry loop needs."""

    result: PublicationResult
    error_code: int | None = None
    retry_after: float | None = None


class TelegramPublisher(Publisher):
    """
    Publishes deals through the Telegram Bot API.

    Uses sendPhoto when the product has an image URL.
    Falls back to sendMessage when no image is available, or when
    sendPhoto failed for a reason Telegram stated explicitly.

    An attempt whose outcome is unknown (network failure, 5xx
    without a JSON body) is never retried and never followed by a
    fallback: the message may already be in the channel (A-2/H2).
    Rate limiting is handled the same way, so a 429 never turns
    into a second message.
    """

    BASE_URL = "https://api.telegram.org"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        formatter: DealMessageFormatter | None = None,
        affiliate_validator: AffiliateLinkValidator | None = None,
        post: Callable[..., Any] = requests.post,
        timeout: float = 15.0,
        *,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.formatter = formatter or DealMessageFormatter()
        self.affiliate_validator = (
            affiliate_validator or AffiliateLinkValidator()
        )
        self.post = post
        self.timeout = timeout
        self._sleep = sleep
        self._rng = rng

    @property
    def send_message_endpoint(self) -> str:
        return (
            f"{self.BASE_URL}/bot"
            f"{self.bot_token}/sendMessage"
        )

    @property
    def send_photo_endpoint(self) -> str:
        return (
            f"{self.BASE_URL}/bot"
            f"{self.bot_token}/sendPhoto"
        )

    @property
    def edit_message_reply_markup_endpoint(self) -> str:
        return (
            f"{self.BASE_URL}/bot"
            f"{self.bot_token}/editMessageReplyMarkup"
        )

    @staticmethod
    def _status_code(response: Any) -> int | None:
        value = getattr(response, "status_code", None)

        if isinstance(value, int) and not isinstance(value, bool):
            return value

        return None

    def _handle_non_json(
        self,
        status_code: int | None,
    ) -> _SendOutcome:
        if status_code == 429:
            return _SendOutcome(
                PublicationResult(
                    success=False,
                    status=STATUS_TELEGRAM_RATE_LIMITED,
                    reason="Telegram rate limit exceeded.",
                ),
                error_code=429,
            )

        if status_code is not None and status_code >= 500:
            # no body to trust: the outcome is unknown
            return _SendOutcome(
                PublicationResult(
                    success=False,
                    status=STATUS_TELEGRAM_HTTP_ERROR,
                    reason=(
                        f"Telegram returned HTTP "
                        f"{status_code}."
                    ),
                    indeterminate=True,
                ),
                error_code=status_code,
            )

        if status_code is not None and status_code >= 400:
            return _SendOutcome(
                PublicationResult(
                    success=False,
                    status=STATUS_TELEGRAM_HTTP_ERROR,
                    reason=(
                        f"Telegram returned HTTP "
                        f"{status_code}."
                    ),
                ),
                error_code=status_code,
            )

        return _SendOutcome(
            PublicationResult(
                success=False,
                status=STATUS_TELEGRAM_INVALID_RESPONSE,
                reason="Telegram returned invalid JSON.",
            )
        )

    @staticmethod
    def _error_code(
        data: dict,
        status_code: int | None,
    ) -> int | None:
        value = data.get("error_code")

        if isinstance(value, int) and not isinstance(value, bool):
            return value

        # Telegram may only signal the problem through the HTTP
        # status (429 / 5xx), even with a JSON body.
        if status_code == 429 or (
            status_code is not None and status_code >= 500
        ):
            return status_code

        return None

    @staticmethod
    def _retry_after(data: dict) -> float | None:
        parameters = data.get("parameters")

        if not isinstance(parameters, dict):
            return None

        value = parameters.get("retry_after")

        if isinstance(value, (int, float)) and not isinstance(
            value, bool
        ):
            return float(value)

        return None

    def _handle_response(
        self,
        response: Any,
    ) -> _SendOutcome:
        status_code = self._status_code(response)

        try:
            data = response.json()
        except ValueError:
            return self._handle_non_json(status_code)

        if not isinstance(data, dict):
            return self._handle_non_json(status_code)

        if not data.get("ok"):
            description = (
                data.get("description")
                or "Telegram API rejected the message."
            )
            error_code = self._error_code(data, status_code)

            if error_code == 429:
                return _SendOutcome(
                    PublicationResult(
                        success=False,
                        status=STATUS_TELEGRAM_RATE_LIMITED,
                        reason=sanitize_text(description),
                    ),
                    error_code=429,
                    retry_after=self._retry_after(data),
                )

            return _SendOutcome(
                PublicationResult(
                    success=False,
                    status=STATUS_TELEGRAM_API_ERROR,
                    reason=sanitize_text(description),
                ),
                error_code=error_code,
                retry_after=self._retry_after(data),
            )

        result = data.get("result")

        message_id = (
            result.get("message_id")
            if isinstance(result, dict)
            else None
        )

        return _SendOutcome(
            PublicationResult(
                success=True,
                status=STATUS_PUBLISHED,
                reason="Deal published successfully.",
                message_id=message_id,
            )
        )

    def _send_attempt(
        self,
        endpoint: str,
        payload: dict,
    ) -> _SendOutcome:
        try:
            response = self.post(
                endpoint,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            # the request may have reached Telegram even though
            # the client saw a failure, so the outcome is unknown;
            # the message (URLs included) never leaves unsanitized
            return _SendOutcome(
                PublicationResult(
                    success=False,
                    status=STATUS_TELEGRAM_REQUEST_ERROR,
                    reason=sanitize_text(str(exc)),
                    indeterminate=True,
                )
            )

        return self._handle_response(response)

    def _retry_delay(
        self,
        outcome: _SendOutcome,
        failed_attempt: int,
    ) -> float | None:
        """Seconds to wait before another call, or None to stop."""
        if outcome.result.indeterminate:
            return None

        if outcome.error_code == 429:
            if outcome.retry_after is not None:
                if outcome.retry_after > RETRY_AFTER_MAX:
                    return None

                return float(outcome.retry_after)

            return compute_backoff(
                TELEGRAM_RETRY_POLICY,
                failed_attempt,
                self._rng,
            )

        if (
            outcome.error_code is not None
            and 500 <= outcome.error_code <= 599
        ):
            return compute_backoff(
                TELEGRAM_RETRY_POLICY,
                failed_attempt,
                self._rng,
            )

        return None

    def _send_with_retry(
        self,
        endpoint: str,
        payload: dict,
    ) -> PublicationResult:
        attempt = 1
        outcome = self._send_attempt(endpoint, payload)

        while not outcome.result.success:
            delay = self._retry_delay(outcome, attempt)

            if (
                delay is None
                or attempt >= TELEGRAM_RETRY_ATTEMPTS
            ):
                break

            logger.warning(
                "telegram retry attempt=%d/%d "
                "delay=%.2fs status=%s",
                attempt,
                TELEGRAM_RETRY_ATTEMPTS,
                delay,
                outcome.result.status,
            )

            self._sleep(delay)

            attempt += 1
            outcome = self._send_attempt(endpoint, payload)

        return outcome.result

    def _reply_markup(self, affiliate_url: str) -> dict:
        return {
            "inline_keyboard": [
                [
                    {
                        "text": "🛒 VER OFERTA",
                        "url": affiliate_url,
                    }
                ]
            ]
        }

    def _build_photo_payload(
        self,
        deal: Deal,
        caption: str,
        reply_markup: dict,
    ) -> dict:
        return {
            "chat_id": self.chat_id,
            "photo": deal.product.image_url,
            "caption": fit_message(
                caption, MAX_CAPTION_LENGTH
            ),
            "parse_mode": "HTML",
            "reply_markup": reply_markup,
        }

    def _build_message_payload(
        self,
        deal: Deal,
        caption: str,
        reply_markup: dict,
    ) -> dict:
        return {
            "chat_id": self.chat_id,
            "text": fit_message(caption, MAX_MESSAGE_LENGTH),
            "parse_mode": "HTML",
            "reply_markup": reply_markup,
        }

    def publish(self, deal: Deal) -> PublicationResult:
        affiliate_result = (
            self.affiliate_validator.validate(
                deal.product
            )
        )

        if not affiliate_result.is_valid:
            return PublicationResult(
                success=False,
                status=affiliate_result.status,
                reason=affiliate_result.reason,
            )

        caption = self.formatter.format(deal)

        reply_markup = self._reply_markup(
            deal.product.affiliate_url
        )

        message_payload = self._build_message_payload(
            deal,
            caption,
            reply_markup,
        )

        if not deal.product.image_url:
            return self._send_with_retry(
                self.send_message_endpoint,
                message_payload,
            )

        photo_payload = self._build_photo_payload(
            deal,
            caption,
            reply_markup,
        )

        photo_result = self._send_with_retry(
            self.send_photo_endpoint,
            photo_payload,
        )

        if photo_result.success:
            return photo_result

        # H2 (A-2): an unknown or rate-limited photo attempt must
        # not be followed by sendMessage - the photo may already
        # be in the channel and a second post would duplicate it.
        if (
            photo_result.indeterminate
            or photo_result.status
            == STATUS_TELEGRAM_RATE_LIMITED
        ):
            return photo_result

        fallback_result = self._send_with_retry(
            self.send_message_endpoint,
            message_payload,
        )

        if fallback_result.success:
            return fallback_result

        if fallback_result.indeterminate:
            # the original photo error is returned so the root
            # cause is preserved, but the outcome is unknown now
            return PublicationResult(
                success=False,
                status=photo_result.status,
                reason=photo_result.reason,
                indeterminate=True,
            )

        return photo_result

    def verify_message(
        self,
        message_id: int,
        *,
        affiliate_url: str,
    ) -> Verdict:
        """Probe the channel for a message sent by an earlier run.

        Setting the identical reply_markup is a read-only probe:
        Telegram answers "message is not modified" when the post
        is still there (EXISTS), and only an explicit "not found"
        is accepted as ABSENT (A-4/A-5). Anything else is
        UNKNOWN - never a guess.
        """
        payload = {
            "chat_id": self.chat_id,
            "message_id": message_id,
            "reply_markup": self._reply_markup(affiliate_url),
        }

        try:
            response = self.post(
                self.edit_message_reply_markup_endpoint,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException:
            return Verdict.UNKNOWN

        try:
            data = response.json()
        except ValueError:
            return Verdict.UNKNOWN

        if not isinstance(data, dict):
            return Verdict.UNKNOWN

        if data.get("ok"):
            return Verdict.EXISTS

        description = str(
            data.get("description") or ""
        ).lower()

        if "message is not modified" in description:
            return Verdict.EXISTS

        error_code = data.get("error_code")

        if error_code == 400 and (
            "message to edit not found" in description
            or "message to delete not found" in description
        ):
            return Verdict.ABSENT

        return Verdict.UNKNOWN
