import re
from urllib.parse import urlparse

from app.models.product import Product
from app.platforms.base import PlatformAdapter


class AmazonAdapter(PlatformAdapter):
    DOMAINS = {
        "amazon.com",
        "www.amazon.com",
        "amazon.com.br",
        "www.amazon.com.br",
    }

    ASIN_PATTERN = re.compile(
        r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})",
        re.IGNORECASE,
    )

    def can_handle(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            hostname = (parsed.hostname or "").lower()
            return hostname in self.DOMAINS
        except Exception:
            return False

    def extract_product_id(self, url: str) -> str | None:
        match = self.ASIN_PATTERN.search(url)

        if not match:
            return None

        return match.group(1).upper()

    def fetch_product(self, url: str) -> Product:
        raise NotImplementedError(
            "Amazon product fetching will be implemented next."
        )
