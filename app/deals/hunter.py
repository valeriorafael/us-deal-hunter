from datetime import datetime
from typing import Optional

from app.deals.scorer import DealScorer
from app.models.deal import Deal
from app.platforms.registry import ProviderRegistry
from app.services.deal_pipeline import DealPipeline


class DealHunter:
    """
    Finds and evaluates deals from product URLs.

    URL
        -> provider registry
        -> product provider
        -> product
        -> record current price
        -> deal pipeline
        -> Deal
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        scorer: Optional[DealScorer] = None,
        pipeline: Optional[DealPipeline] = None,
    ):
        self.registry = registry
        self.scorer = scorer or DealScorer()
        self.pipeline = pipeline or DealPipeline()

    def analyze(
    self,
    url: str,
    now: datetime | None = None,
) -> Optional[Deal]:
        provider = self.registry.get_provider(url)

        if provider is None:
            return None

        product = provider.get_product(url)

        if product is None:
            return None

        self.pipeline.record_price(product, now=now)

        return self.pipeline.evaluate(product, now=now)
