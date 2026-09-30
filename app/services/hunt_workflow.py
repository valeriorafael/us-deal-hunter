from dataclasses import dataclass
from datetime import datetime

from app.models.deal import Deal
from app.publication.base import PublicationResult
from app.publication.service import PublicationService
from app.services.discovery_workflow import DiscoveryWorkflow
from app.services.hunt_policy import HuntPublicationPolicy


@dataclass(frozen=True)
class HuntResult:
    discovered_count: int
    published_count: int
    results: tuple[PublicationResult, ...]


class HuntWorkflow:
    """
    Executes the complete deal-hunting flow.
    """

    def __init__(
        self,
        discovery_workflow: DiscoveryWorkflow,
        publication_service: PublicationService,
        policy: HuntPublicationPolicy | None = None,
    ):
        self.discovery_workflow = discovery_workflow
        self.publication_service = publication_service
        self.policy = policy or HuntPublicationPolicy()

    def publish_deals(
        self,
        deals: list[Deal],
        now: datetime | None = None,
    ) -> HuntResult:
        results = []
        published_count = 0

        for deal in deals:
            if (
                published_count
                >= self.policy.max_publications_per_run
            ):
                break

            result = self.publication_service.publish(
                deal,
                now=now,
            )

            results.append(result)

            if result.success:
                published_count += 1

        return HuntResult(
            discovered_count=len(deals),
            published_count=published_count,
            results=tuple(results),
        )

    def discover_and_publish(
        self,
        keywords: str,
        search_index: str = "All",
        item_count: int = 10,
        item_page: int = 1,
        min_saving_percent: float | None = None,
        now: datetime | None = None,
    ) -> HuntResult:
        deals = self.discovery_workflow.discover_deals(
            keywords=keywords,
            search_index=search_index,
            item_count=item_count,
            item_page=item_page,
            min_saving_percent=min_saving_percent,
            now=now,
        )

        return self.publish_deals(
            deals,
            now=now,
        )
