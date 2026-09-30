from dataclasses import dataclass
from typing import Protocol

from app.models.deal import Deal


@dataclass(frozen=True)
class PublicationResult:
    success: bool
    status: str
    reason: str
    message_id: int | None = None


class Publisher(Protocol):
    def publish(self, deal: Deal) -> PublicationResult:
        ...
