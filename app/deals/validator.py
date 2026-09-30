from dataclasses import dataclass

from app.deals.affiliate_validator import AffiliateLinkValidator
from app.models.deal import Deal


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    status: str
    reason: str


class DealValidator:
    """
    Decides whether a scored Deal has enough evidence
    to be considered a real deal.
    """

    def __init__(
        self,
        affiliate_validator: AffiliateLinkValidator | None = None,
    ):
        self.affiliate_validator = (
            affiliate_validator or AffiliateLinkValidator()
        )

    def validate(self, deal: Deal) -> ValidationResult:

        if deal.confidence == "LOW":
            return ValidationResult(
                is_valid=False,
                status="INSUFFICIENT_HISTORY",
                reason="Insufficient historical price data.",
            )

        if deal.confidence == "MEDIUM":
            return ValidationResult(
                is_valid=False,
                status="UNCERTAIN",
                reason="Historical price data is incomplete.",
            )

        if deal.score < 60:
            return ValidationResult(
                is_valid=False,
                status="LOW_SCORE",
                reason="Deal score is below the minimum threshold.",
            )

        affiliate_result = self.affiliate_validator.validate(
            deal.product
        )

        if not affiliate_result.is_valid:
            return ValidationResult(
                is_valid=False,
                status=affiliate_result.status,
                reason=affiliate_result.reason,
            )

        return ValidationResult(
            is_valid=True,
            status="VALID",
            reason="Deal has sufficient history and a strong score.",
        )
