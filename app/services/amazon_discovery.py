from typing import Any

from app.models.product import Product
from app.platforms.amazon_client import AmazonApiClient
from app.platforms.amazon_parser import AmazonProductParser


class AmazonDiscovery:
    """
    Discovers Amazon products through Creators API SearchItems.
    """

    def __init__(
        self,
        client: AmazonApiClient | None = None,
        parser: AmazonProductParser | None = None,
    ):
        self.client = (
            client or AmazonApiClient()
        )
        self.parser = (
            parser or AmazonProductParser()
        )

    @staticmethod
    def _extract_image_url(
        item: dict[str, Any],
    ) -> str:
        images = (
            item.get("images")
            or item.get("Images")
            or {}
        )

        primary = (
            images.get("primary")
            or images.get("Primary")
            or {}
        )

        large = (
            primary.get("large")
            or primary.get("Large")
            or {}
        )

        return (
            large.get("url")
            or large.get("URL")
            or ""
        )

    def discover(
        self,
        keywords: str,
        search_index: str = "All",
        item_count: int = 10,
        item_page: int = 1,
        min_saving_percent: float | None = None,
    ) -> list[Product]:
        data = self.client.search_items(
            keywords=keywords,
            search_index=search_index,
            item_count=item_count,
            item_page=item_page,
            min_saving_percent=min_saving_percent,
        )

        if not data:
            return []

        search_result = (
            data.get("searchResult")
            or data.get("SearchResult")
            or {}
        )

        items = (
            search_result.get("items")
            or search_result.get("Items")
            or []
        )

        products = []

        for item in items:
            if not isinstance(item, dict):
                continue

            product = self.parser.parse(
                {
                    "itemsResult": {
                        "items": [item]
                    }
                }
            )

            if product is None:
                continue

            affiliate_url = (
                item.get("detailPageURL")
                or item.get("DetailPageURL")
                or ""
            )

            product.platform = "amazon"
            product.product_url = affiliate_url
            product.affiliate_url = affiliate_url
            product.image_url = (
                self._extract_image_url(item)
            )

            products.append(product)

        return products