from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from app.models.deal import Deal

# Single source of truth for the deduplication policy. A product
# (ASIN) is only published again once this window has fully
# elapsed since its last successful publication.
DEFAULT_PUBLICATION_COOLDOWN = timedelta(hours=24)


@dataclass(frozen=True)
class PublicationResult:
    success: bool
    status: str
    reason: str
    message_id: int | None = None


class Publisher(Protocol):
    def publish(self, deal: Deal) -> PublicationResult:
        ...
