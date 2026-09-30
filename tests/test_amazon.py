import pytest

from app.platforms.amazon import AmazonAdapter


@pytest.fixture
def amazon():
    return AmazonAdapter()


def test_recognizes_amazon_com(amazon):
    assert amazon.can_handle(
        "https://www.amazon.com/dp/B08N5WRWNW"
    )


def test_recognizes_amazon_com_br(amazon):
    assert amazon.can_handle(
        "https://www.amazon.com.br/dp/B08N5WRWNW"
    )


def test_rejects_other_platform(amazon):
    assert not amazon.can_handle(
        "https://www.shopee.com/product/123"
    )


def test_extracts_asin_from_dp_url(amazon):
    assert amazon.extract_product_id(
        "https://www.amazon.com/dp/B08N5WRWNW"
    ) == "B08N5WRWNW"


def test_extracts_asin_from_product_url(amazon):
    assert amazon.extract_product_id(
        "https://www.amazon.com/gp/product/B08N5WRWNW"
    ) == "B08N5WRWNW"


def test_extracts_asin_case_insensitively(amazon):
    assert amazon.extract_product_id(
        "https://www.amazon.com/dp/b08n5wrwnw"
    ) == "B08N5WRWNW"


def test_returns_none_when_no_asin(amazon):
    assert amazon.extract_product_id(
        "https://www.amazon.com/some-page"
    ) is None


def test_fetch_product_not_implemented_yet(amazon):
    with pytest.raises(NotImplementedError):
        amazon.fetch_product(
            "https://www.amazon.com/dp/B08N5WRWNW"
        )
