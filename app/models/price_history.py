from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PriceHistory:
    product_id: str
    price: float
    currency: str = "USD"
    recorded_at: datetime | None = None

    def __post_init__(self):
        if not self.product_id:
            raise ValueError("product_id cannot be empty")

        if self.price <= 0:
            raise ValueError("price must be greater than zero")

        if self.recorded_at is None:
            object.__setattr__(
                self,
                "recorded_at",
                datetime.now(),
            )
