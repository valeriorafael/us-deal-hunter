from datetime import datetime, timedelta

from app.publication.base import DEFAULT_PUBLICATION_COOLDOWN
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


def test_was_published_detects_any_prior_publication(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    published_at = datetime(2026, 8, 15, 12, 0)

    assert repository.was_published("123") is False

    repository.record(
        product_id="123",
        affiliate_url="https://example.com/123",
        price=75.0,
        published_at=published_at,
    )

    assert repository.was_published("123") is True


def test_was_published_has_no_time_limit(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    published_at = datetime(2026, 8, 15, 12, 0)
    now = published_at + timedelta(days=400)

    repository.record(
        product_id="123",
        affiliate_url="https://example.com/123",
        price=75.0,
        published_at=published_at,
    )

    assert repository.was_published("123") is True
    assert repository.was_published_recently(
        "123",
        now=now,
    ) is False


def test_publication_repository_cooldown_boundary_is_exclusive(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    published_at = datetime(2026, 8, 15, 12, 0)
    cooldown = DEFAULT_PUBLICATION_COOLDOWN

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=published_at,
    )

    assert repository.was_published_recently(
        "123",
        now=published_at + cooldown - timedelta(seconds=1),
    ) is True

    assert repository.was_published_recently(
        "123",
        now=published_at + cooldown,
    ) is False

    assert repository.was_published_recently(
        "123",
        now=published_at + timedelta(hours=25),
    ) is False


def test_publication_repository_uses_latest_publication_for_cooldown(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    old = datetime(2026, 8, 14, 10, 0)
    recent = datetime(2026, 8, 15, 10, 0)
    now = datetime(2026, 8, 15, 11, 0)

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=old,
    )

    assert repository.was_published_recently(
        "123",
        now=now,
    ) is False

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=70.0,
        published_at=recent,
    )

    assert repository.was_published_recently(
        "123",
        now=now,
    ) is True


def test_repository_default_cooldown_is_exactly_24_hours(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    published_at = datetime(2026, 8, 15, 12, 0)
    cooldown = timedelta(hours=24)

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=published_at,
    )

    assert (
        repository.was_published_recently(
            "123",
            now=(
                published_at
                + cooldown
                - timedelta(microseconds=1)
            ),
        )
        is True
    )

    assert (
        repository.was_published_recently(
            "123",
            now=(
                published_at
                + cooldown
                + timedelta(microseconds=1)
            ),
        )
        is False
    )


def test_failed_record_does_not_block_cooldown(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    failed_at = datetime(2026, 8, 15, 12, 0)

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=failed_at,
        status="FAILED",
    )

    assert repository.was_published_recently(
        "123",
        now=failed_at + timedelta(hours=1),
    ) is False

    assert repository.was_published("123") is False


def test_was_published_isolates_products(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com/123",
        price=75.0,
        published_at=datetime(2026, 8, 15, 12, 0),
    )

    assert repository.was_published("123") is True
    assert repository.was_published("456") is False
    assert repository.was_published("does-not-exist") is False
