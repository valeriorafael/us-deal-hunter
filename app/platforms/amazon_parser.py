from typing import Any

from app.models.product import Product


class AmazonProductParser:

    def parse(self, payload: dict[str, Any]) -> Product | None:
        items_result = payload.get("ItemsResult", {})
        items = items_result.get("Items", [])

        if not items:
            return None

        item = items[0]

        product_id = item.get("ASIN")

        if not product_id:
            return None

        title = (
            item.get("ItemInfo", {})
            .get("Title", {})
            .get("DisplayValue")
        )

        if not title:
            title = "Unknown Product"

        listings = (
            item.get("Offers", {})
            .get("Listings", [])
        )

        if not listings:
            return None

        price_data = (
            listings[0]
            .get("Price", {})
        )

        amount = price_data.get("Amount")

        if amount is None:
            return None

        currency = price_data.get(
            "Currency",
            "USD",
        )

        return Product(
            product_id=product_id,
            title=title,
            current_price=float(amount),
            currency=currency,
            platform="amazon",
        )
