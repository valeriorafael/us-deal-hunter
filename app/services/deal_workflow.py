from datetime import datetime

from app.deals.hunter import DealHunter
from app.models.deal import Deal
from app.publication.base import PublicationResult
from app.publication.service import PublicationService


class DealWorkflow:
    """
    Coordinates deal analysis and optional publication.

    URL
        -> DealHunter
        -> Deal
        -> PublicationService
    """

    def __init__(
        self,
        hunter: DealHunter,
        publication_service: PublicationService,
    ):
        self.hunter = hunter
        self.publication_service = publication_service

    def analyze(
        self,
        url: str,
        now: datetime | None = None,
    ) -> Deal | None:
        return self.hunter.analyze(
            url,
            now=now,
        )

    def analyze_and_publish(
        self,
        url: str,
        now: datetime | None = None,
    ) -> PublicationResult:
        deal = self.analyze(
            url,
            now=now,
        )

        if deal is None:
            return PublicationResult(
                success=False,
                status="NO_DEAL",
                reason="No valid deal was found.",
            )

        return self.publication_service.publish(
            deal,
            now=now,
        )
