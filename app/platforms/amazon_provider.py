from typing import Optional

from app.models.product import Product
from app.platforms.amazon import AmazonAdapter
from app.platforms.amazon_client import AmazonApiClient
from app.platforms.amazon_parser import AmazonProductParser
from app.platforms.provider import ProductProvider


class AmazonProvider(ProductProvider):
    """
    Product provider backed by Amazon Creators API.
    """

    def __init__(
        self,
        client: Optional[AmazonApiClient] = None,
        adapter: Optional[AmazonAdapter] = None,
        parser: Optional[AmazonProductParser] = None,
    ):
        self.client = client or AmazonApiClient()
        self.adapter = adapter or AmazonAdapter()
        self.parser = parser or AmazonProductParser()

    def get_product(self, url: str) -> Optional[Product]:
        if not self.adapter.can_handle(url):
            return None

        asin = self.adapter.extract_product_id(url)

        if asin is None:
            return None

        data = self.client.get_items(asin)

        if data is None:
            return None

        return self._to_product(
            data=data,
            url=url,
            asin=asin,
        )

    def _to_product(
        self,
        data: dict,
        url: str,
        asin: str,
    ) -> Optional[Product]:
        product = self.parser.parse(data)

        if product is None:
            return None

        product.platform = "amazon"
        product.product_url = url
        product.affiliate_url = url

        return product
