from app.services.image_resolver import ImageResolver


class FakeResponse:
    def __init__(
        self,
        html,
        url="https://example.com/deal",
    ):
        self.text = html
        self.url = url

    def raise_for_status(self):
        pass


def test_image_resolver_reads_og_image():
    def fake_get(url, timeout, headers):
        return FakeResponse(
            """
            <html>
                <head>
                    <meta
                        property="og:image"
                        content="/images/product.jpg"
                    >
                </head>
            </html>
            """,
            url="https://example.com/deal",
        )

    resolver = ImageResolver(
        get=fake_get
    )

    result = resolver.resolve(
        "https://example.com/deal"
    )

    assert result == (
        "https://example.com/images/product.jpg"
    )


def test_image_resolver_accepts_twitter_image():
    def fake_get(url, timeout, headers):
        return FakeResponse(
            """
            <meta
                name="twitter:image"
                content="https://cdn.example.com/item.jpg"
            >
            """
        )

    resolver = ImageResolver(
        get=fake_get
    )

    result = resolver.resolve(
        "https://example.com/deal"
    )

    assert result == (
        "https://cdn.example.com/item.jpg"
    )


def test_image_resolver_returns_empty_when_not_found():
    def fake_get(url, timeout, headers):
        return FakeResponse(
            "<html><body>No image</body></html>"
        )

    resolver = ImageResolver(
        get=fake_get
    )

    assert (
        resolver.resolve(
            "https://example.com/deal"
        )
        == ""
    )

def test_image_resolver_logs_unexpected_candidate_errors(
    caplog,
):
    import logging

    def exploding_get(url, timeout, headers):
        raise ValueError("unexpected parser failure")

    resolver = ImageResolver(get=exploding_get)

    with caplog.at_level(
        logging.WARNING,
        logger="app.services.image_resolver",
    ):
        assert resolver.resolve("https://example.com/deal") == ""

    assert "image candidate failed" in caplog.text
    assert "unexpected parser failure" in caplog.text
