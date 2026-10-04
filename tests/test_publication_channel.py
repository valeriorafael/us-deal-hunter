from datetime import datetime, timedelta

from app.models.deal import Deal
from app.models.product import Product
from app.publication.base import (
    CHANNEL_TELEGRAM,
    CHANNEL_WEBSITE,
    STATUS_PUBLICATION_ERROR,
    PublicationResult,
)
from app.publication.service import PublicationService
from app.publication.website import WebsitePublisher
from app.services import database
from app.services.database import connect
from app.services.publication_repository import (
    PublicationRepository,
)

NOW = datetime(2026, 8, 15, 12, 0)


def build_valid_deal(product_id="123"):
    product = Product(
        product_id=product_id,
        title="Test Product",
        current_price=75.0,
        average_price_30d=100.0,
        lowest_price_90d=70.0,
        rating=4.7,
        review_count=8500,
        platform="amazon",
        affiliate_url=(
            f"https://www.amazon.com/dp/{product_id}?tag=test-20"
        ),
    )

    return Deal(
        product=product,
        score=88.0,
        label="GREAT",
        confidence="HIGH",
    )


class FakePublisher:
    def __init__(self, message_id=123):
        self.message_id = message_id
        self.calls = []

    def publish(self, deal):
        self.calls.append(deal)

        return PublicationResult(
            success=True,
            status="PUBLISHED",
            reason="Published.",
            message_id=self.message_id,
        )


# ------------------------------------------------------------------
# A) Migration 5
# ------------------------------------------------------------------


def test_migration_5_adds_channel_column(tmp_path):
    connection = connect(str(tmp_path / "channel.db"))

    info = connection.execute(
        "PRAGMA table_info(publications)"
    ).fetchall()
    connection.close()

    columns = {row[1]: row for row in info}

    assert "channel" in columns
    # NOT NULL with a literal default: type, notnull, default
    assert columns["channel"][2] == "TEXT"
    assert columns["channel"][3] == 1
    assert columns["channel"][4] == "'TELEGRAM'"


def test_migration_5_sets_user_version_to_latest(tmp_path):
    connection = connect(str(tmp_path / "version.db"))

    version = connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0]
    connection.close()

    assert version >= 5
    assert version == database.LATEST_SCHEMA_VERSION


def test_migration_5_backfills_legacy_rows_with_telegram(
    tmp_path,
    monkeypatch,
):
    db_path = str(tmp_path / "legacy_channel.db")
    original = database.MIGRATIONS

    # Build a version-4 database with one publication row.
    monkeypatch.setattr(
        database,
        "MIGRATIONS",
        tuple(
            migration
            for migration in original
            if migration.version <= 4
        ),
    )

    legacy = connect(db_path)
    legacy.execute(
        """
        INSERT INTO publications (
            product_id, affiliate_url, price,
            published_at, status
        ) VALUES ('B00001', 'https://example.com', 99.5,
                  '2026-08-15T12:00:00', 'PUBLISHED')
        """
    )
    legacy.commit()
    legacy.close()

    monkeypatch.setattr(database, "MIGRATIONS", original)

    # Applying migration 5 backfills the existing row.
    migrated = connect(db_path)
    rows = migrated.execute(
        "SELECT product_id, channel FROM publications"
    ).fetchall()
    version = migrated.execute(
        "PRAGMA user_version"
    ).fetchone()[0]
    migrated.close()

    assert rows == [("B00001", CHANNEL_TELEGRAM)]
    assert version == database.LATEST_SCHEMA_VERSION


def test_migration_5_is_idempotent_on_reopen(tmp_path):
    db_path = str(tmp_path / "reopen_channel.db")

    connect(db_path).close()
    reopened = connect(db_path)

    channel_columns = [
        row
        for row in reopened.execute(
            "PRAGMA table_info(publications)"
        ).fetchall()
        if row[1] == "channel"
    ]
    version = reopened.execute(
        "PRAGMA user_version"
    ).fetchone()[0]
    reopened.close()

    assert len(channel_columns) == 1
    assert version == database.LATEST_SCHEMA_VERSION


def test_migration_5_creates_channel_index(tmp_path):
    connection = connect(str(tmp_path / "index_channel.db"))

    index = connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'index' AND name = ?",
        ("idx_publications_channel_product_published",),
    ).fetchone()
    connection.close()

    assert index is not None
    assert index[0] == "idx_publications_channel_product_published"


# ------------------------------------------------------------------
# B) Repository
# ------------------------------------------------------------------


def test_record_writes_default_channel(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "record.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com/dp/123",
        price=75.0,
        published_at=NOW,
    )

    rows = repository._connection.execute(
        "SELECT channel FROM publications"
    ).fetchall()
    repository.close()

    assert rows == [(CHANNEL_TELEGRAM,)]


def test_record_writes_explicit_channel(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "record_website.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com/dp/123",
        price=75.0,
        published_at=NOW,
        channel=CHANNEL_WEBSITE,
    )

    rows = repository._connection.execute(
        "SELECT channel FROM publications"
    ).fetchall()
    repository.close()

    assert rows == [(CHANNEL_WEBSITE,)]


def test_begin_attempt_writes_channel(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "attempt_default.db")
    )

    attempt_id = repository.begin_attempt(
        product_id="123",
        affiliate_url="https://example.com/dp/123",
        price=75.0,
        attempted_at=NOW,
    )
    website_id = repository.begin_attempt(
        product_id="456",
        affiliate_url="https://example.com/dp/456",
        price=50.0,
        attempted_at=NOW,
        channel=CHANNEL_WEBSITE,
    )

    rows = dict(
        repository._connection.execute(
            "SELECT id, channel FROM publications"
        ).fetchall()
    )
    repository.close()

    assert rows[attempt_id] == CHANNEL_TELEGRAM
    assert rows[website_id] == CHANNEL_WEBSITE


def test_begin_attempt_exclusive_preserves_channel(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "exclusive.db")
    )

    attempt_id = repository.begin_attempt_exclusive(
        duplicate_check=lambda: False,
        product_id="123",
        affiliate_url="https://example.com/dp/123",
        price=75.0,
        attempted_at=NOW,
        channel=CHANNEL_WEBSITE,
    )

    assert attempt_id is not None

    stored_channel = repository._connection.execute(
        "SELECT channel FROM publications WHERE id = ?",
        (attempt_id,),
    ).fetchone()[0]

    assert stored_channel == CHANNEL_WEBSITE

    rejected = repository.begin_attempt_exclusive(
        duplicate_check=lambda: True,
        product_id="456",
        affiliate_url="https://example.com/dp/456",
        price=50.0,
        attempted_at=NOW,
        channel=CHANNEL_WEBSITE,
    )
    repository.close()

    assert rejected is None


def test_was_published_is_channel_scoped(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "was_published.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com/dp/123",
        price=75.0,
        published_at=NOW,
    )

    assert repository.was_published("123") is True
    assert (
        repository.was_published(
            "123", channel=CHANNEL_WEBSITE
        )
        is False
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com/dp/123",
        price=75.0,
        published_at=NOW,
        channel=CHANNEL_WEBSITE,
    )

    assert (
        repository.was_published(
            "123", channel=CHANNEL_WEBSITE
        )
        is True
    )
    repository.close()


def test_was_published_recently_is_channel_scoped(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "cooldown.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com/dp/123",
        price=75.0,
        published_at=NOW,
    )

    assert (
        repository.was_published_recently("123", now=NOW)
        is True
    )
    assert (
        repository.was_published_recently(
            "123",
            now=NOW,
            channel=CHANNEL_WEBSITE,
        )
        is False
    )
    repository.close()


def test_has_inflight_attempt_is_channel_scoped(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "inflight.db")
    )

    repository.begin_attempt(
        product_id="123",
        affiliate_url="https://example.com/dp/123",
        price=75.0,
        attempted_at=NOW,
    )

    assert repository.has_inflight_attempt("123") is True
    assert (
        repository.has_inflight_attempt(
            "123", channel=CHANNEL_WEBSITE
        )
        is False
    )
    repository.close()


def test_attempts_for_verification_is_channel_scoped(tmp_path):
    db_path = str(tmp_path / "verify_channel.db")
    repository = PublicationRepository(db_path)

    telegram_id = repository.begin_attempt(
        product_id="111",
        affiliate_url="https://example.com/dp/111",
        price=10.0,
        attempted_at=NOW,
    )
    repository.mark_sending(telegram_id)

    website_id = repository.begin_attempt(
        product_id="222",
        affiliate_url="https://example.com/dp/222",
        price=20.0,
        attempted_at=NOW,
        channel=CHANNEL_WEBSITE,
    )
    repository.mark_sending(website_id)

    repository._connection.execute(
        "UPDATE publications SET message_id = 42"
    )
    repository._connection.commit()

    window = {
        "stale_before": NOW + timedelta(hours=1),
        "not_older_than": NOW - timedelta(days=1),
        "limit": 10,
    }

    telegram_rows = repository.attempts_for_verification(
        **window,
    )
    website_rows = repository.attempts_for_verification(
        **window,
        channel=CHANNEL_WEBSITE,
    )
    repository.close()

    assert [r.product_id for r in telegram_rows] == ["111"]
    assert [r.product_id for r in website_rows] == ["222"]


# ------------------------------------------------------------------
# C) Isolation between channels
# ------------------------------------------------------------------


def test_telegram_publication_does_not_block_website(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "isolation1.db")
    )
    deal = build_valid_deal()

    telegram = PublicationService(
        publisher=FakePublisher(),
        repository=repository,
        channel=CHANNEL_TELEGRAM,
    )
    website = PublicationService(
        publisher=FakePublisher(message_id=456),
        repository=repository,
        channel=CHANNEL_WEBSITE,
    )

    first = telegram.publish(deal, now=NOW)
    second = website.publish(deal, now=NOW + timedelta(hours=1))

    assert first.success is True
    assert second.success is True
    assert second.status == "PUBLISHED"
    repository.close()


def test_website_publication_does_not_block_telegram(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "isolation2.db")
    )
    deal = build_valid_deal()

    website = PublicationService(
        publisher=FakePublisher(),
        repository=repository,
        channel=CHANNEL_WEBSITE,
    )
    telegram = PublicationService(
        publisher=FakePublisher(message_id=456),
        repository=repository,
        channel=CHANNEL_TELEGRAM,
    )

    first = website.publish(deal, now=NOW)
    second = telegram.publish(deal, now=NOW + timedelta(hours=1))

    assert first.success is True
    assert second.success is True
    assert second.status == "PUBLISHED"
    repository.close()


def test_telegram_cooldown_does_not_affect_website(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "cooldown_iso.db")
    )

    repository.record(
        product_id="123",
        affiliate_url="https://example.com/dp/123",
        price=75.0,
        published_at=NOW,
    )

    assert (
        repository.was_published_recently(
            "123",
            now=NOW + timedelta(hours=1),
            channel=CHANNEL_WEBSITE,
        )
        is False
    )

    assert (
        repository.was_published_recently(
            "123",
            now=NOW + timedelta(hours=1),
        )
        is True
    )
    repository.close()


def test_telegram_inflight_does_not_affect_website(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "inflight_iso.db")
    )
    deal = build_valid_deal()

    repository.begin_attempt(
        product_id="123",
        affiliate_url="https://example.com/dp/123",
        price=75.0,
        attempted_at=NOW,
    )

    telegram = PublicationService(
        publisher=FakePublisher(),
        repository=repository,
        channel=CHANNEL_TELEGRAM,
    )
    website = PublicationService(
        publisher=FakePublisher(message_id=456),
        repository=repository,
        channel=CHANNEL_WEBSITE,
    )

    blocked = telegram.publish(deal, now=NOW)
    allowed = website.publish(deal, now=NOW)

    assert blocked.success is False
    assert blocked.status == "DUPLICATE_PUBLICATION"
    assert allowed.success is True
    repository.close()


# ------------------------------------------------------------------
# D) PublicationService
# ------------------------------------------------------------------


def test_two_services_share_database_independently(tmp_path):
    db_path = str(tmp_path / "shared.db")
    repository = PublicationRepository(db_path)
    deal = build_valid_deal()

    publisher_tg = FakePublisher()
    publisher_web = FakePublisher(message_id=456)

    telegram = PublicationService(
        publisher=publisher_tg,
        repository=repository,
        channel=CHANNEL_TELEGRAM,
    )
    website = PublicationService(
        publisher=publisher_web,
        repository=repository,
        channel=CHANNEL_WEBSITE,
    )

    first = telegram.publish(deal, now=NOW)
    second = website.publish(deal, now=NOW)

    # The same product on one channel blocks only that channel.
    third = telegram.publish(deal, now=NOW + timedelta(hours=1))

    channels = [
        row[0]
        for row in repository._connection.execute(
            "SELECT channel FROM publications ORDER BY id"
        ).fetchall()
    ]
    repository.close()

    assert first.success is True
    assert second.success is True
    assert len(publisher_tg.calls) == 1
    assert len(publisher_web.calls) == 1
    assert third.success is False
    assert third.status == "DUPLICATE_PUBLICATION"
    assert channels == [CHANNEL_TELEGRAM, CHANNEL_WEBSITE]
    assert first.message_id == 123
    assert second.message_id == 456


def test_service_default_channel_is_telegram(tmp_path):
    db_path = str(tmp_path / "default_channel.db")
    repository = PublicationRepository(db_path)
    deal = build_valid_deal()

    service = PublicationService(
        publisher=FakePublisher(),
        repository=repository,
    )

    assert service.channel == CHANNEL_TELEGRAM

    first = service.publish(deal, now=NOW)
    second = service.publish(deal, now=NOW + timedelta(hours=1))

    rows = repository._connection.execute(
        "SELECT channel FROM publications"
    ).fetchall()
    repository.close()

    assert first.success is True
    assert second.success is False
    assert second.status == "DUPLICATE_PUBLICATION"
    assert rows == [(CHANNEL_TELEGRAM,)]


def test_legacy_positional_calls_remain_supported(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "positional.db")
    )

    repository.record(
        "123",
        "https://example.com/dp/123",
        75.0,
        NOW,
    )

    assert repository.was_published("123") is True
    assert repository.has_inflight_attempt("123") is False
    repository.close()


# ------------------------------------------------------------------
# E) Isolation with the real WebsitePublisher
# ------------------------------------------------------------------


class CountingWebsitePublisher(WebsitePublisher):
    """Real publisher plus a call counter (spy, no state kept)."""

    def __init__(self):
        self.calls = []

    def publish(self, deal):
        self.calls.append(deal)

        return super().publish(deal)


def test_real_website_publication_does_not_block_telegram(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "real_website_first.db")
    )
    deal = build_valid_deal()

    website = PublicationService(
        publisher=WebsitePublisher(),
        repository=repository,
        channel=CHANNEL_WEBSITE,
    )
    telegram = PublicationService(
        publisher=FakePublisher(message_id=456),
        repository=repository,
        channel=CHANNEL_TELEGRAM,
    )

    first = website.publish(deal, now=NOW)
    second = telegram.publish(deal, now=NOW + timedelta(hours=1))
    repository.close()

    assert first.success is True
    assert first.message_id is None
    assert second.success is True
    assert second.message_id == 456


def test_real_telegram_publication_does_not_block_website(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "real_telegram_first.db")
    )
    deal = build_valid_deal()

    telegram = PublicationService(
        publisher=FakePublisher(),
        repository=repository,
        channel=CHANNEL_TELEGRAM,
    )
    website = PublicationService(
        publisher=WebsitePublisher(),
        repository=repository,
        channel=CHANNEL_WEBSITE,
    )

    first = telegram.publish(deal, now=NOW)
    second = website.publish(deal, now=NOW + timedelta(hours=1))
    repository.close()

    assert first.success is True
    assert second.success is True
    assert second.status == "PUBLISHED"


def test_real_website_publication_stays_channel_scoped(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "real_website_scope.db")
    )
    deal = build_valid_deal()

    result = PublicationService(
        publisher=WebsitePublisher(),
        repository=repository,
        channel=CHANNEL_WEBSITE,
    ).publish(deal, now=NOW)

    telegram_scope = repository.was_published(deal.product.product_id)
    website_scope = repository.was_published(
        deal.product.product_id, channel=CHANNEL_WEBSITE
    )
    repository.close()

    assert result.success is True
    assert telegram_scope is False
    assert website_scope is True


def test_real_website_rejected_url_does_not_block_telegram(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "real_website_rejected.db")
    )
    broken = build_valid_deal()
    # non-Amazon platform so DealValidator accepts the deal and the
    # website publisher is the one rejecting the URL
    broken.product.platform = "other"
    broken.product.affiliate_url = "notaurl"

    website = PublicationService(
        publisher=WebsitePublisher(),
        repository=repository,
        channel=CHANNEL_WEBSITE,
    )
    telegram = PublicationService(
        publisher=FakePublisher(message_id=456),
        repository=repository,
        channel=CHANNEL_TELEGRAM,
    )

    rejected = website.publish(broken, now=NOW)
    accepted = telegram.publish(build_valid_deal(), now=NOW)
    rows = repository._connection.execute(
        "SELECT channel, status FROM publications ORDER BY id"
    ).fetchall()
    repository.close()

    assert rejected.success is False
    assert rejected.status == STATUS_PUBLICATION_ERROR
    assert accepted.success is True
    assert rows == [(CHANNEL_TELEGRAM, "PUBLISHED")]


# ------------------------------------------------------------------
# F) Idempotence with the real WebsitePublisher
# ------------------------------------------------------------------


def test_real_website_publisher_called_once_within_cooldown(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "website_cooldown_once.db")
    )
    deal = build_valid_deal()
    publisher = CountingWebsitePublisher()

    service = PublicationService(
        publisher=publisher,
        repository=repository,
        channel=CHANNEL_WEBSITE,
    )

    first = service.publish(deal, now=NOW)
    second = service.publish(deal, now=NOW + timedelta(hours=1))
    repository.close()

    assert first.success is True
    assert first.status == "PUBLISHED"
    assert second.success is False
    assert second.status == "DUPLICATE_PUBLICATION"
    # the rule belongs to PublicationService: the publisher is
    # invoked once and holds no state of its own
    assert len(publisher.calls) == 1


def test_real_website_publisher_republishes_after_cooldown(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "website_cooldown_expired.db")
    )
    deal = build_valid_deal()
    publisher = CountingWebsitePublisher()

    service = PublicationService(
        publisher=publisher,
        repository=repository,
        channel=CHANNEL_WEBSITE,
    )

    first = service.publish(deal, now=NOW)
    second = service.publish(deal, now=NOW + timedelta(hours=25))
    repository.close()

    assert first.success is True
    assert second.success is True
    assert len(publisher.calls) == 2


def test_real_website_publisher_is_stateless_across_products(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "website_two_products.db")
    )
    publisher = CountingWebsitePublisher()

    service = PublicationService(
        publisher=publisher,
        repository=repository,
        channel=CHANNEL_WEBSITE,
    )

    first = service.publish(build_valid_deal("111"), now=NOW)
    second = service.publish(build_valid_deal("222"), now=NOW)
    repository.close()

    assert first.success is True
    assert second.success is True
    assert len(publisher.calls) == 2
