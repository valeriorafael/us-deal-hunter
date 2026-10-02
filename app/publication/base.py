from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Protocol

from app.models.deal import Deal

# Single source of truth for the deduplication policy. A product
# (ASIN) is only published again once this window has fully
# elapsed since its last successful publication.
DEFAULT_PUBLICATION_COOLDOWN = timedelta(hours=24)

# Attempt row lifecycle (spec 16): PENDING -> SENDING ->
# PUBLISHED, or RECONCILIATION when the outcome is unknown.
STATUS_PENDING = "PENDING"
STATUS_SENDING = "SENDING"
STATUS_PUBLISHED = "PUBLISHED"
STATUS_RECONCILIATION = "RECONCILIATION"

# Publication service outcomes.
STATUS_DUPLICATE_PUBLICATION = "DUPLICATE_PUBLICATION"
STATUS_PUBLICATION_ERROR = "PUBLICATION_ERROR"
STATUS_PUBLICATION_EXCEPTION = "PUBLICATION_EXCEPTION"
STATUS_PUBLICATION_STORE_ERROR = "PUBLICATION_STORE_ERROR"

# Telegram publisher outcomes (phase 4).
STATUS_TELEGRAM_API_ERROR = "TELEGRAM_API_ERROR"
STATUS_TELEGRAM_HTTP_ERROR = "TELEGRAM_HTTP_ERROR"
STATUS_TELEGRAM_INVALID_RESPONSE = "TELEGRAM_INVALID_RESPONSE"
STATUS_TELEGRAM_REQUEST_ERROR = "TELEGRAM_REQUEST_ERROR"
STATUS_TELEGRAM_RATE_LIMITED = "TELEGRAM_RATE_LIMITED"

# Statuses counted as a failed publication attempt. Duplicates and
# validation failures are deliberately excluded: they are expected
# outcomes, not faults.
FAILURE_STATUSES = frozenset(
    {
        STATUS_PUBLICATION_ERROR,
        STATUS_PUBLICATION_EXCEPTION,
        STATUS_PUBLICATION_STORE_ERROR,
        STATUS_TELEGRAM_API_ERROR,
        STATUS_TELEGRAM_HTTP_ERROR,
        STATUS_TELEGRAM_INVALID_RESPONSE,
        STATUS_TELEGRAM_REQUEST_ERROR,
        STATUS_TELEGRAM_RATE_LIMITED,
    }
)


def is_failure_status(status: str) -> bool:
    """True for statuses the run must surface as errors."""
    return status in FAILURE_STATUSES


@dataclass(frozen=True)
class PublicationResult:
    success: bool
    status: str
    reason: str
    message_id: int | None = None
    # True when it is impossible to know whether the message was
    # delivered (network failure after the request left, crash).
    # PublicationService keeps the attempt row as RECONCILIATION
    # instead of deleting it.
    indeterminate: bool = False


class Publisher(Protocol):
    def publish(self, deal: Deal) -> PublicationResult:
        ...

class Verdict(Enum):
    """Result of probing the channel for a sent message (spec 17).

    EXISTS  - the message is in the channel (publish recovered).
    ABSENT  - Telegram explicitly reported it was deleted.
    UNKNOWN - probe failed; nothing may be assumed (spec 25).
    """

    EXISTS = "EXISTS"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


class MessageVerifier(Protocol):
    def verify_message(
        self,
        message_id: int,
        *,
        affiliate_url: str,
    ) -> Verdict:
        ...
