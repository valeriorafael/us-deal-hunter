from typing import Any

from app.models.product import Product


class AmazonProductParser:

    def parse(self, payload: dict[str, Any]) -> Product | None:
        items_result = payload.get("ItemsResult")

        if items_result is None:
            items_result = payload.get("itemsResult", {})

        items = items_result.get("Items")

        if items is None:
            items = items_result.get("items", [])

        if not items:
            return None

        item = items[0]

        product_id = item.get("ASIN")

        if product_id is None:
            product_id = item.get("asin")

        if not product_id:
            return None

        title = self._parse_title(item)

        if not title:
            title = "Unknown Product"

        amount, currency = self._parse_price(item)

        if amount is None:
            return None

        return Product(
            product_id=product_id,
            title=title,
            current_price=float(amount),
            currency=currency,
            platform="amazon",
        )

    def _parse_title(self, item: dict[str, Any]) -> str | None:
        item_info = item.get("ItemInfo")

        if item_info is None:
            item_info = item.get("itemInfo", {})

        title_data = item_info.get("Title")

        if title_data is None:
            title_data = item_info.get("title", {})

        return title_data.get("DisplayValue") or title_data.get(
            "displayValue"
        )

    def _parse_price(
        self,
        item: dict[str, Any],
    ) -> tuple[float | None, str]:
        # Formato legado / testes atuais.
        offers = item.get("Offers")

        if offers is not None:
            listings = offers.get("Listings", [])

            if listings:
                price = listings[0].get("Price", {})
                amount = price.get("Amount")

                if amount is not None:
                    return (
                        float(amount),
                        price.get("Currency", "USD"),
                    )

        # Formato atual da Creators API / SDK.
        offers_v2 = item.get("offersV2", {})

        listings = offers_v2.get("listings", [])

        if listings:
            price = listings[0].get("price", {})
            amount = price.get("amount")

            if amount is not None:
                return (
                    float(amount),
                    price.get("currency", "USD"),
                )

        return None, "USD"