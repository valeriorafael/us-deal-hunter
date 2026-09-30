from typing import Any, Callable

import requests

from app.deals.affiliate_validator import AffiliateLinkValidator
from app.models.deal import Deal
from app.publication.base import PublicationResult, Publisher
from app.publication.formatter import DealMessageFormatter


class TelegramPublisher(Publisher):
    """
    Publishes deals through the Telegram Bot API.

    Uses sendPhoto when the product has an image URL.
    Falls back to sendMessage when no image is available.

    When an image URL is present but sendPhoto fails, the
    publication is retried once as sendMessage. If that retry
    also fails, the original sendPhoto error is returned so
    the root cause is preserved.
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
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.formatter = formatter or DealMessageFormatter()
        self.affiliate_validator = (
            affiliate_validator or AffiliateLinkValidator()
        )
        self.post = post
        self.timeout = timeout

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

    def _handle_response(
        self,
        response: Any,
    ) -> PublicationResult:
        try:
            data = response.json()
        except ValueError:
            status_code = getattr(
                response,
                "status_code",
                0,
            )

            if status_code >= 400:
                return PublicationResult(
                    success=False,
                    status="TELEGRAM_HTTP_ERROR",
                    reason=(
                        f"Telegram returned HTTP "
                        f"{status_code}."
                    ),
                )

            return PublicationResult(
                success=False,
                status="TELEGRAM_INVALID_RESPONSE",
                reason="Telegram returned invalid JSON.",
            )

        if not data.get("ok"):
            return PublicationResult(
                success=False,
                status="TELEGRAM_API_ERROR",
                reason=data.get(
                    "description",
                    "Telegram API rejected the message.",
                ),
            )

        result = data.get("result") or {}

        return PublicationResult(
            success=True,
            status="PUBLISHED",
            reason="Deal published successfully.",
            message_id=result.get("message_id"),
        )

    def _build_photo_payload(
        self,
        deal: Deal,
        caption: str,
        reply_markup: dict,
    ) -> dict:
        return {
            "chat_id": self.chat_id,
            "photo": deal.product.image_url,
            "caption": caption,
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
            "text": caption,
            "parse_mode": "HTML",
            "reply_markup": reply_markup,
        }

    def _send(
        self,
        endpoint: str,
        payload: dict,
    ) -> PublicationResult:
        try:
            response = self.post(
                endpoint,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            return PublicationResult(
                success=False,
                status="TELEGRAM_REQUEST_ERROR",
                reason=str(exc),
            )

        return self._handle_response(response)

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

        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "🛒 VER OFERTA",
                        "url": deal.product.affiliate_url,
                    }
                ]
            ]
        }

        message_payload = self._build_message_payload(
            deal,
            caption,
            reply_markup,
        )

        if not deal.product.image_url:
            return self._send(
                self.send_message_endpoint,
                message_payload,
            )

        photo_payload = self._build_photo_payload(
            deal,
            caption,
            reply_markup,
        )

        photo_result = self._send(
            self.send_photo_endpoint,
            photo_payload,
        )

        if photo_result.success:
            return photo_result

        fallback_result = self._send(
            self.send_message_endpoint,
            message_payload,
        )

        if not fallback_result.success:
            return photo_result

        return fallback_result