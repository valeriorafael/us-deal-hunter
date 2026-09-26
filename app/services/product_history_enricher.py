from datetime import datetime

from app.models.price_history import PriceHistory
from app.models.product import Product
from app.services.price_history import PriceHistoryService


class ProductHistoryEnricher:
    def enrich(
        self,
        product: Product,
        history: list[PriceHistory],
        now: datetime | None = None,
    ) -> Product:
        service = PriceHistoryService(
            history,
            product_id=product.product_id,
        )

        product.average_price_30d = service.average_price(
            days=30,
            now=now,
        )

        product.lowest_price_90d = service.lowest_price(
            days=90,
            now=now,
        )

        product.price_history_days = service.history_days(
            now=now,
        )

        return product
