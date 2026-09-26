from app.platforms.platform import PlatformDetector
from app.platforms.provider import ProductProvider


class ProviderRegistry:
    """
    Selects the appropriate product provider based on the product URL.
    """

    def __init__(
        self,
        providers: dict[str, ProductProvider],
        detector: PlatformDetector | None = None,
    ):
        self.providers = providers
        self.detector = detector or PlatformDetector()

    def get_provider(self, url: str) -> ProductProvider | None:
        match = self.detector.detect(url)

        if match is None:
            return None

        return self.providers.get(match.platform)
