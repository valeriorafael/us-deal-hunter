import pytest

from app.platforms.provider import ProductProvider


def test_product_provider_is_abstract():
    with pytest.raises(TypeError):
        ProductProvider()


def test_product_provider_requires_get_product():
    class IncompleteProvider(ProductProvider):
        pass

    with pytest.raises(TypeError):
        IncompleteProvider()
