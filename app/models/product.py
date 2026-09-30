from dataclasses import dataclass
from typing import Optional


@dataclass
class Product:
    product_id: str
    title: str
    current_price: float
    currency: str = "USD"

    average_price_30d: Optional[float] = None
    lowest_price_90d: Optional[float] = None
    price_history_days: Optional[int] = None

    rating: Optional[float] = None
    review_count: int = 0

    platform: str = ""
    product_url: str = ""
    affiliate_url: str = ""
    image_url: str = ""

    @property
    def discount_vs_30d(self) -> Optional[float]:
        if self.average_price_30d is None:
            return None

        if self.average_price_30d <= 0:
            return None

        return (
            (self.average_price_30d - self.current_price)
            / self.average_price_30d
        )

    @property
    def distance_from_90d_low(self) -> Optional[float]:
        if self.lowest_price_90d is None:
            return None

        if self.lowest_price_90d <= 0:
            return None

        return (
            (self.current_price - self.lowest_price_90d)
            / self.lowest_price_90d
        )