from app.models.product import Product
from app.platforms.fake_amazon import FakeAmazonProvider


class DemoAmazonDiscovery:
    """
    Demo discovery source using the built-in fake Amazon provider.

    It does not call Amazon or any external API.
    """

    def __init__(
        self,
        provider: FakeAmazonProvider | None = None,
    ):
        self.provider = provider or FakeAmazonProvider()

    def discover(
        self,
        keywords: str,
        search_index: str = "All",
        item_count: int = 10,
        item_page: int = 1,
        min_saving_percent: float | None = None,
    ) -> list[Product]:
        normalized = keywords.strip().lower()

        if "gaming mouse" not in normalized:
            return []

        products = list(
            self.provider.products.values()
        )

        return products[:item_count]
