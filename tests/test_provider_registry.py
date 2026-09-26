from app.platforms.fake_amazon import FakeAmazonProvider
from app.platforms.registry import ProviderRegistry


def test_registry_selects_amazon_provider():
    provider = FakeAmazonProvider()

    registry = ProviderRegistry(
        providers={
            "amazon": provider,
        }
    )

    result = registry.get_provider(
        "https://www.amazon.com/dp/B08N5WRWNW"
    )

    assert result is provider


def test_registry_returns_none_for_unknown_platform():
    registry = ProviderRegistry(
        providers={
            "amazon": FakeAmazonProvider(),
        }
    )

    result = registry.get_provider(
        "https://example.com/product/123"
    )

    assert result is None


def test_registry_returns_none_when_platform_has_no_provider():
    registry = ProviderRegistry(
        providers={}
    )

    result = registry.get_provider(
        "https://www.amazon.com/dp/B08N5WRWNW"
    )

    assert result is None
