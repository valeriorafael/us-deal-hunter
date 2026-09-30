from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse
import re


@dataclass
class PlatformMatch:
    platform: str
    product_id: Optional[str] = None


class PlatformDetector:
    """Detects supported e-commerce platforms from product URLs."""

    AMAZON_DOMAINS = {
        "amazon.com",
        "www.amazon.com",
        "amazon.co.uk",
        "www.amazon.co.uk",
        "amazon.de",
        "www.amazon.de",
        "amazon.ca",
        "www.amazon.ca",
    }

    def detect(self, url: str) -> Optional[PlatformMatch]:
        """Detect platform and product ID from a URL."""

        try:
            parsed = urlparse(url)
        except Exception:
            return None

        if parsed.scheme not in ("http", "https"):
            return None

        domain = parsed.netloc.lower().split(":")[0]

        if domain in self.AMAZON_DOMAINS:
            product_id = self._extract_amazon_id(parsed.path)

            if product_id:
                return PlatformMatch(
                    platform="amazon",
                    product_id=product_id,
                )

            return PlatformMatch(platform="amazon")

        return None

    @staticmethod
    def _extract_amazon_id(path: str) -> Optional[str]:
        """Extract ASIN from common Amazon URL formats."""

        patterns = [
            r"/dp/([A-Z0-9]{10})",
            r"/gp/product/([A-Z0-9]{10})",
            r"/gp/aw/d/([A-Z0-9]{10})",
        ]

        for pattern in patterns:
            match = re.search(pattern, path, re.IGNORECASE)

            if match:
                return match.group(1).upper()

        return None
