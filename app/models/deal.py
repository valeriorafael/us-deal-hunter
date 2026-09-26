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

    @property
    def discount_vs_30d(self) -> Optional[float]:
        return self.product.discount_vs_30d

    @property
    def distance_from_90d_low(self) -> Optional[float]:
        return self.product.distance_from_90d_low

    @property
    def is_deal(self) -> bool:
        return self.score >= 60.0
