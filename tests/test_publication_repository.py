from datetime import datetime, timedelta

from app.services.publication_repository import (
    PublicationRepository,
)


def test_publication_repository_records_publication(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    now = datetime(2026, 8, 15, 12, 0)

    repository.record(
        product_id="123",
        affiliate_url=(
            "https://www.amazon.com/dp/123?tag=test-20"
        ),
        price=75.0,
        published_at=now,
    )

    assert repository.count("123") == 1


def test_publication_repository_detects_recent_publication(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    now = datetime(2026, 8, 15, 12, 0)

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=now,
    )

    assert repository.was_published_recently(
        "123",
        now=now,
    ) is True


def test_publication_repository_allows_publication_after_cooldown(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    published_at = datetime(2026, 8, 15, 12, 0)
    now = published_at + timedelta(hours=25)

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=published_at,
    )

    assert repository.was_published_recently(
        "123",
        now=now,
    ) is False


def test_publication_repository_tracks_products_independently(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    now = datetime(2026, 8, 15, 12, 0)

    repository.record(
        product_id="123",
        affiliate_url="https://example.com/123",
        price=75.0,
        published_at=now,
    )

    assert repository.was_published_recently(
        "123",
        now=now,
    ) is True

    assert repository.was_published_recently(
        "456",
        now=now,
    ) is False
