from app.deals.affiliate_validator import AffiliateLinkValidator
from app.models.product import Product


def test_amazon_product_without_affiliate_link_is_invalid():
    product = Product(
        product_id="123",
        title="Amazon Product",
        current_price=75.0,
        platform="amazon",
    )

    result = AffiliateLinkValidator().validate(product)

    assert result.is_valid is False
    assert result.status == "MISSING_AFFILIATE_LINK"


def test_amazon_product_with_affiliate_link_is_valid():
    product = Product(
        product_id="123",
        title="Amazon Product",
        current_price=75.0,
        platform="amazon",
        affiliate_url=(
            "https://www.amazon.com/dp/123?tag=testtag-20"
        ),
    )

    result = AffiliateLinkValidator().validate(product)

    assert result.is_valid is True
    assert result.status == "VALID"


def test_non_amazon_product_does_not_require_affiliate_link():
    product = Product(
        product_id="123",
        title="Other Product",
        current_price=75.0,
        platform="other",
    )

    result = AffiliateLinkValidator().validate(product)

    assert result.is_valid is True
    assert result.status == "VALID"
