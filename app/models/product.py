from dataclasses import dataclass
from typing import Optional


@dataclass
class Product:
    """Normalized product representation used by the deal engine."""

    product_id: str
    title: str
    current_price: float
    currency: str = "USD"

    average_price_30d: Optional[float] = None
    lowest_price_90d: Optional[float] = None

    rating: Optional[float] = None
    review_count: int = 0

    platform: str = "amazon"
    product_url: str = ""
    affiliate_url: str = ""

    @property
    def discount_vs_30d(self) -> Optional[float]:
        """Return discount relative to the 30-day average."""
        if self.average_price_30d is None or self.average_price_30d <= 0:
            return None

        return (
            (self.average_price_30d - self.current_price)
            / self.average_price_30d
        )

    @property
    def distance_from_90d_low(self) -> Optional[float]:
        """Return how far current price is above the 90-day low."""
        if self.lowest_price_90d is None or self.lowest_price_90d <= 0:
            return None

        return (
            (self.current_price - self.lowest_price_90d)
            / self.lowest_price_90d
        )

