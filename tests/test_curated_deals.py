import json

from app.services.curated_deals import CuratedDealLoader


class FakeImageResolver:
    def resolve(
        self,
        source_url,
        fallback_urls=None,
    ):
        assert source_url == "https://example.com/deal"

        assert fallback_urls == [
            "https://www.amazon.com/dp/B123456789"
        ]

        return (
            "https://cdn.example.com/product.jpg"
        )


def test_curated_loader_resolves_image_automatically(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AMAZON_PARTNER_TAG",
        "test-20",
    )

    path = tmp_path / "curated.json"

    path.write_text(
        json.dumps(
            {
                "max_publications_per_run": 3,
                "deals": [
                    {
                        "asin": "B123456789",
                        "title": "Test Product",
                        "current_price": 50.0,
                        "reference_price": 70.0,
                        "rating": 4.5,
                        "review_count": 100,
                        "source_name": "Test Source",
                        "source_url": (
                            "https://example.com/deal"
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loader = CuratedDealLoader(
        image_resolver=FakeImageResolver()
    )

    config = loader.load(
        str(path)
    )

    assert len(config.deals) == 1

    deal = config.deals[0]

    assert deal.product.image_url == (
        "https://cdn.example.com/product.jpg"
    )


def test_curated_loader_keeps_explicit_image(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AMAZON_PARTNER_TAG",
        "test-20",
    )

    path = tmp_path / "curated.json"

    path.write_text(
        json.dumps(
            {
                "deals": [
                    {
                        "asin": "B123456789",
                        "title": "Test Product",
                        "current_price": 50.0,
                        "reference_price": 70.0,
                        "source_name": "Test Source",
                        "source_url": (
                            "https://example.com/deal"
                        ),
                        "image_url": (
                            "https://cdn.example.com/"
                            "explicit.jpg"
                        ),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class FailingResolver:
        def resolve(
            self,
            source_url,
            fallback_urls=None,
        ):
            raise AssertionError(
                "Resolver should not be called."
            )

    loader = CuratedDealLoader(
        image_resolver=FailingResolver()
    )

    config = loader.load(
        str(path)
    )

    assert config.deals[0].product.image_url == (
        "https://cdn.example.com/explicit.jpg"
    )

def test_curated_loader_missing_file_raises_value_error(
    tmp_path,
    monkeypatch,
):
    import pytest

    monkeypatch.setenv(
        "AMAZON_PARTNER_TAG",
        "test-20",
    )

    loader = CuratedDealLoader()

    with pytest.raises(
        ValueError,
        match="Curated deals file not found",
    ):
        loader.load(
            str(tmp_path / "missing.json")
        )


def test_curated_loader_invalid_json_raises_value_error(
    tmp_path,
    monkeypatch,
):
    import pytest

    monkeypatch.setenv(
        "AMAZON_PARTNER_TAG",
        "test-20",
    )

    path = tmp_path / "curated.json"
    path.write_text("{not json", encoding="utf-8")

    loader = CuratedDealLoader()

    with pytest.raises(
        ValueError,
        match="Invalid curated deals JSON",
    ):
        loader.load(str(path))


def test_curated_loader_reports_invalid_deal_index(
    tmp_path,
    monkeypatch,
):
    import pytest

    monkeypatch.setenv(
        "AMAZON_PARTNER_TAG",
        "test-20",
    )

    path = tmp_path / "curated.json"

    path.write_text(
        json.dumps(
            {
                "deals": [
                    {
                        "asin": "B123456789",
                        "current_price": 50.0,
                        "reference_price": 70.0,
                        "source_name": "Test Source",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loader = CuratedDealLoader()

    with pytest.raises(
        ValueError,
        match=r"Invalid curated deal #1",
    ):
        loader.load(str(path))
