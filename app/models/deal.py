from dataclasses import dataclass
from typing import Optional

from app.models.product import Product


@dataclass
class Deal:
    """Represents a product opportunity evaluated by the deal engine."""

    product: Product

    score: float = 0.0
    label: str = "UNKNOWN"
    reasons: tuple[str, ...] = ()
    confidence: str = "LOW"
    source_query: str | None = None
    reference_price: float | None = None
    source_name: str | None = None
    source_url: str | None = None

    @property
    def discount_vs_30d(self) -> Optional[float]:
        return self.product.discount_vs_30d

    @property
    def distance_from_90d_low(self) -> Optional[float]:
        return self.product.distance_from_90d_low

    @property
    def reference_discount(self) -> float | None:
        if (
            self.reference_price is None
            or self.reference_price <= self.product.current_price
        ):
            return None

        return (
            self.reference_price - self.product.current_price
        ) / self.reference_price

    @property
    def is_deal(self) -> bool:
        return self.score >= 60.0