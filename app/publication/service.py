from datetime import datetime, timedelta

from app.deals.validator import DealValidator
from app.models.deal import Deal
from app.publication.base import PublicationResult, Publisher
from app.services.publication_repository import (
    PublicationRepository,
)


class PublicationService:
    """
    Coordinates deal validation, deduplication and publication.

    Deal
        -> validation
        -> duplicate check
        -> publisher
        -> publication record
    """

    def __init__(
        self,
        publisher: Publisher,
        deal_validator: DealValidator | None = None,
        repository: PublicationRepository | None = None,
        cooldown: timedelta = timedelta(hours=24),
    ):
        self.publisher = publisher
        self.deal_validator = (
            deal_validator or DealValidator()
        )
        self.repository = (
            repository or PublicationRepository()
        )
        self.cooldown = cooldown

    def publish(
        self,
        deal: Deal,
        now: datetime | None = None,
    ) -> PublicationResult:
        now = now or datetime.now()

        validation = self.deal_validator.validate(deal)

        if not validation.is_valid:
            return PublicationResult(
                success=False,
                status=validation.status,
                reason=validation.reason,
            )

        if self.repository.was_published_recently(
            product_id=deal.product.product_id,
            now=now,
            cooldown=self.cooldown,
        ):
            return PublicationResult(
                success=False,
                status="DUPLICATE_PUBLICATION",
                reason="Product was published recently.",
            )

        result = self.publisher.publish(deal)

        if not result.success:
            return result

        self.repository.record(
            product_id=deal.product.product_id,
            affiliate_url=deal.product.affiliate_url,
            price=deal.product.current_price,
            published_at=now,
            title=deal.product.title,
            score=deal.score,
            label=deal.label,
            discount_vs_30d=deal.discount_vs_30d,
            source_query=deal.source_query,
        )

        return result