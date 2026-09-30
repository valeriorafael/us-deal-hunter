from dataclasses import dataclass

from app.models.product import Product


@dataclass(frozen=True)
class AffiliateValidationResult:
    is_valid: bool
    status: str
    reason: str


class AffiliateLinkValidator:
    """
    Validates whether a product has the affiliate link required
    for publication.
    """

    def validate(self, product: Product) -> AffiliateValidationResult:
        if (
            product.platform == "amazon"
            and not product.affiliate_url.strip()
        ):
            return AffiliateValidationResult(
                is_valid=False,
                status="MISSING_AFFILIATE_LINK",
                reason="Amazon affiliate link is missing.",
            )

        return AffiliateValidationResult(
            is_valid=True,
            status="VALID",
            reason="Affiliate link is available.",
        )
