from typing import Optional

from app.models.product import Product
from app.platforms.provider import ProductProvider


class FakeAmazonProvider(ProductProvider):

    def __init__(self):
        self.products = {
            "B08N5WRWNW": Product(
                product_id="B08N5WRWNW",
                title="Test Product",
                current_price=75.0,
                currency="USD",
                average_price_30d=100.0,
                lowest_price_90d=70.0,
                rating=4.7,
                review_count=8500,
                platform="amazon",
                product_url="https://www.amazon.com/dp/B08N5WRWNW",
                affiliate_url="https://www.amazon.com/dp/B08N5WRWNW?tag=test",
            )
        }

    def get_product(self, url: str) -> Optional[Product]:
        product_id = self._extract_product_id(url)

        if product_id is None:
            return None

        return self.products.get(product_id)

    def _extract_product_id(self, url: str) -> Optional[str]:
        import re

        match = re.search(
            r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})",
            url,
            re.IGNORECASE,
        )

        if not match:
            return None

        return match.group(1).upper()
