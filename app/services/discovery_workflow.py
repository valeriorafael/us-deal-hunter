import logging
from datetime import datetime

from app.models.deal import Deal
from app.services.amazon_discovery import AmazonDiscovery
from app.services.deal_pipeline import DealPipeline
from app.services.run_summary import sanitize_error

logger = logging.getLogger(__name__)


class DiscoveryWorkflow:
    """
    Discovers products and evaluates them as deals.

    Search
        -> Products
        -> Price History
        -> Scoring
        -> Valid Deals
    """

    def __init__(
        self,
        discovery: AmazonDiscovery,
        pipeline: DealPipeline,
    ):
        self.discovery = discovery
        self.pipeline = pipeline
        # errors of individual products, formatted for the
        # runner SUMMARY (spec phase 3, section 9); the runner
        # drains this list after every keyword
        self.product_errors: list[str] = []

    def discover_deals(
        self,
        keywords: str,
        search_index: str = "All",
        item_count: int = 10,
        item_page: int = 1,
        min_saving_percent: float | None = None,
        now: datetime | None = None,
    ) -> list[Deal]:
        products = self.discovery.discover(
            keywords=keywords,
            search_index=search_index,
            item_count=item_count,
            item_page=item_page,
            min_saving_percent=min_saving_percent,
        )

        deals: list[Deal] = []
        processed_ids: set[str] = set()

        for product in products:
            if product.product_id in processed_ids:
                continue

            processed_ids.add(product.product_id)

            try:
                self.pipeline.record_price(
                    product,
                    now=now,
                )

                deal = self.pipeline.evaluate(
                    product,
                    now=now,
                )
            except Exception as exc:
                # one broken product must not abort the
                # whole discovery flow
                message = sanitize_error(exc)

                logger.warning(
                    "product %s failed: %s",
                    product.product_id,
                    message,
                )
                self.product_errors.append(
                    f"product: {product.product_id} "
                    f"@ {keywords}: {message}"
                )
                continue

            if deal is not None:
                deal.source_query = keywords
                deals.append(deal)

        return sorted(
            deals,
            key=lambda deal: deal.score,
            reverse=True,
        )