from datetime import datetime

from app.deals.scorer import DealScorer
from app.deals.validator import DealValidator
from app.models.deal import Deal
from app.models.product import Product
from app.models.price_history import PriceHistory
from app.services.price_history_repository import PriceHistoryRepository
from app.services.product_history_enricher import ProductHistoryEnricher


class DealPipeline:
    """
    Orchestrates the complete deal evaluation process.

    Product
        -> repository history
        -> history enrichment
        -> scoring
        -> validation
        -> Deal or None
    """

    def __init__(self, repository: PriceHistoryRepository | None = None):
        self.repository = repository or PriceHistoryRepository()
        self.enricher = ProductHistoryEnricher()
        self.scorer = DealScorer()
        self.validator = DealValidator()

    def record_price(
        self,
        product: Product,
        now: datetime | None = None,
    ) -> None:
        recorded_at = now or datetime.now()

        self.repository.save(
            PriceHistory(
                product_id=product.product_id,
                price=product.current_price,
                currency=product.currency,
                recorded_at=recorded_at,
            )
        )

    def evaluate(
        self,
        product: Product,
        history=None,
        now: datetime | None = None,
    ) -> Deal | None:

        # 1. Load historical prices from the repository when
        # history is not explicitly supplied.
        if history is None:
            history = self.repository.get_by_product(
                product.product_id
            )

        # 2. Enrich product with historical information.
        enriched_product = self.enricher.enrich(
            product,
            history,
            now=now,
        )

        # 3. Calculate deal score.
        deal = self.scorer.evaluate(enriched_product)

        # 4. Validate the scored opportunity.
        result = self.validator.validate(deal)

        # 5. Only valid deals leave the pipeline.
        if not result.is_valid:
            return None

        return deal
