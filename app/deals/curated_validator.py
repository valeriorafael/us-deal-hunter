from app.deals.affiliate_validator import AffiliateLinkValidator
from app.deals.validator import ValidationResult
from app.models.deal import Deal


class CuratedDealValidator:
    """
    Validates deals that were verified from a current external
    deal source and whose Amazon URL is generated with our
    Partner Tag.
    """

    def __init__(
        self,
        affiliate_validator: AffiliateLinkValidator | None = None,
        minimum_discount: float = 0.15,
    ):
        self.affiliate_validator = (
            affiliate_validator or AffiliateLinkValidator()
        )
        self.minimum_discount = minimum_discount

    def validate(self, deal: Deal) -> ValidationResult:
        affiliate_result = (
            self.affiliate_validator.validate(
                deal.product
            )
        )

        if not affiliate_result.is_valid:
            return ValidationResult(
                is_valid=False,
                status=affiliate_result.status,
                reason=affiliate_result.reason,
            )

        if not deal.source_name:
            return ValidationResult(
                is_valid=False,
                status="MISSING_DEAL_SOURCE",
                reason="Curated deal source is missing.",
            )

        if deal.reference_discount is None:
            return ValidationResult(
                is_valid=False,
                status="INVALID_REFERENCE_PRICE",
                reason="Reference price is invalid.",
            )

        if deal.reference_discount < self.minimum_discount:
            return ValidationResult(
                is_valid=False,
                status="LOW_CURATED_DISCOUNT",
                reason="Curated discount is below the minimum.",
            )

        return ValidationResult(
            is_valid=True,
            status="VALID",
            reason=(
                "Curated Amazon deal has a verified "
                "current price, reference price, source, "
                "and affiliate link."
            ),
        )