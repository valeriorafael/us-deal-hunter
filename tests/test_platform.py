from app.platforms.platform import PlatformDetector


def test_detect_amazon_dp():
    detector = PlatformDetector()

    result = detector.detect(
        "https://www.amazon.com/dp/B0ABC12345"
    )

    assert result is not None
    assert result.platform == "amazon"
    assert result.product_id == "B0ABC12345"


def test_detect_amazon_gp_product():
    detector = PlatformDetector()

    result = detector.detect(
        "https://www.amazon.com/gp/product/B0ABC12345"
    )

    assert result is not None
    assert result.platform == "amazon"
    assert result.product_id == "B0ABC12345"


def test_detect_amazon_without_product_id():
    detector = PlatformDetector()

    result = detector.detect(
        "https://www.amazon.com/"
    )

    assert result is not None
    assert result.platform == "amazon"
    assert result.product_id is None


def test_unknown_platform():
    detector = PlatformDetector()

    result = detector.detect(
        "https://example.com/product/123"
    )

    assert result is None


def test_invalid_scheme():
    detector = PlatformDetector()

    result = detector.detect(
        "ftp://www.amazon.com/dp/B0ABC12345"
    )

    assert result is None
