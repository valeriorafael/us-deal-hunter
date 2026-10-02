import logging
from dataclasses import dataclass
from datetime import datetime

from app.models.deal import Deal
from app.publication.base import (
    STATUS_DUPLICATE_PUBLICATION,
    STATUS_PUBLICATION_ERROR,
    PublicationResult,
)
from app.publication.service import PublicationService
from app.services.discovery_workflow import DiscoveryWorkflow
from app.services.hunt_policy import HuntPublicationPolicy
from app.services.resilience import Deadline
from app.services.run_summary import sanitize_error

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HuntResult:
    discovered_count: int
    published_count: int
    results: tuple[PublicationResult, ...]
    attempted_count: int = 0
    failed_count: int = 0
    duplicate_count: int = 0
    deadline_exceeded: bool = False


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
        *,
        deadline: Deadline | None = None,
    ) -> HuntResult:
        results = []
        published_count = 0
        deadline_exceeded = False

        for deal in deals:
            if (
                published_count
                >= self.policy.max_publications_per_run
            ):
                break

            if deadline is not None and deadline.expired:
                logger.warning(
                    "deadline reached before publishing %s",
                    deal.product.product_id,
                )
                deadline_exceeded = True
                break

            try:
                result = self.publication_service.publish(
                    deal,
                    now=now,
                )
            except Exception as exc:
                # a fault in the publication path must never
                # abort the run or hide the other deals
                logger.error(
                    "publication failed for %s: %s",
                    deal.product.product_id,
                    sanitize_error(exc),
                )

                result = PublicationResult(
                    success=False,
                    status=STATUS_PUBLICATION_ERROR,
                    reason=sanitize_error(exc),
                )

            results.append(result)

            if result.success:
                published_count += 1

        attempted_count = len(results)

        return HuntResult(
            discovered_count=len(deals),
            published_count=published_count,
            results=tuple(results),
            attempted_count=attempted_count,
            failed_count=attempted_count - published_count,
            duplicate_count=sum(
                1
                for item in results
                if item.status == (
                    STATUS_DUPLICATE_PUBLICATION
                )
            ),
            deadline_exceeded=deadline_exceeded,
        )

    def discover_and_publish(
        self,
        keywords: str,
        search_index: str = "All",
        item_count: int = 10,
        item_page: int = 1,
        min_saving_percent: float | None = None,
        now: datetime | None = None,
        *,
        deadline: Deadline | None = None,
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
            deadline=deadline,
        )
