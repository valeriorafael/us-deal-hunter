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


def test_publication_repository_closes_connection(tmp_path):
    import sqlite3

    import pytest

    db_path = tmp_path / "context.db"

    with PublicationRepository(str(db_path)) as repository:
        repository.record(
            product_id="123",
            affiliate_url="https://example.com",
            price=75.0,
            published_at=datetime(2026, 8, 15, 12, 0),
        )

        assert repository.count("123") == 1

    with pytest.raises(sqlite3.ProgrammingError):
        repository.count("123")

    repository.close()


def _fetch(repository, attempt_id):
    return repository._connection.execute(
        """
        SELECT status, published_at, message_id
        FROM publications
        WHERE id = ?
        """,
        (attempt_id,),
    ).fetchone()


def test_begin_attempt_creates_pending_row(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    attempted_at = datetime(2026, 8, 15, 12, 0)

    attempt_id = repository.begin_attempt(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        attempted_at=attempted_at,
        title="Deal",
        score=88.0,
        label="GREAT",
        discount_vs_30d=0.25,
        source_query="mouse",
    )

    status, published_at, message_id = _fetch(
        repository, attempt_id
    )

    assert isinstance(attempt_id, int)
    assert status == "PENDING"
    assert published_at == attempted_at.isoformat()
    assert message_id is None
    assert repository.count("123") == 1


def test_begin_attempt_persists_image_url(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    attempt_id = repository.begin_attempt(
        product_id="B0IMG1",
        affiliate_url="https://example.com",
        price=39.95,
        attempted_at=datetime(2026, 8, 15, 12, 0),
        image_url="https://images.example.com/lego.jpg",
    )

    row = repository._connection.execute(
        "SELECT image_url FROM publications WHERE id = ?",
        (attempt_id,),
    ).fetchone()

    assert (
        row[0] == "https://images.example.com/lego.jpg"
    )


def test_begin_attempt_without_image_stores_null(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    attempt_id = repository.begin_attempt(
        product_id="B0NOIMG",
        affiliate_url="https://example.com",
        price=39.95,
        attempted_at=datetime(2026, 8, 15, 12, 0),
    )

    row = repository._connection.execute(
        "SELECT image_url FROM publications WHERE id = ?",
        (attempt_id,),
    ).fetchone()

    assert row[0] is None


def test_attempt_lifecycle_reaches_published(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    started = datetime(2026, 8, 15, 12, 0)
    succeeded = datetime(2026, 8, 15, 12, 0, 3)

    attempt_id = repository.begin_attempt(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        attempted_at=started,
    )

    repository.mark_sending(attempt_id)

    assert _fetch(repository, attempt_id)[0] == "SENDING"

    repository.mark_published(
        attempt_id, succeeded, message_id=777
    )

    status, published_at, message_id = _fetch(
        repository, attempt_id
    )

    assert status == "PUBLISHED"
    assert published_at == succeeded.isoformat()
    assert message_id == 777
    assert repository.was_published("123") is True


def test_drop_attempt_removes_the_row(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    attempt_id = repository.begin_attempt(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        attempted_at=datetime(2026, 8, 15, 12, 0),
    )

    repository.mark_sending(attempt_id)
    repository.drop_attempt(attempt_id)

    assert _fetch(repository, attempt_id) is None
    assert repository.count("123") == 0
    assert repository.was_published("123") is False


def test_mark_unknown_sets_reconciliation(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    attempt_id = repository.begin_attempt(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        attempted_at=datetime(2026, 8, 15, 12, 0),
    )

    repository.mark_sending(attempt_id)
    repository.mark_unknown(attempt_id)

    status, _, message_id = _fetch(repository, attempt_id)

    assert status == "RECONCILIATION"
    assert message_id is None


def test_reconcile_stale_attempts_resolves_orphans(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    now = datetime(2026, 8, 15, 12, 0)
    stale = now - timedelta(seconds=601)
    fresh = now - timedelta(seconds=599)

    stale_pending = repository.begin_attempt(
        product_id="A1",
        affiliate_url="https://example.com",
        price=10.0,
        attempted_at=stale,
    )
    stale_sending = repository.begin_attempt(
        product_id="A2",
        affiliate_url="https://example.com",
        price=10.0,
        attempted_at=stale,
    )
    repository.mark_sending(stale_sending)

    fresh_sending = repository.begin_attempt(
        product_id="A3",
        affiliate_url="https://example.com",
        price=10.0,
        attempted_at=fresh,
    )
    repository.mark_sending(fresh_sending)

    repository.record(
        product_id="A4",
        affiliate_url="https://example.com",
        price=10.0,
        published_at=stale,
    )

    resolved = repository.reconcile_stale_attempts(
        older_than=now - timedelta(seconds=600)
    )

    assert resolved == 2
    assert _fetch(repository, stale_pending)[0] == (
        "RECONCILIATION"
    )
    assert _fetch(repository, stale_sending)[0] == (
        "RECONCILIATION"
    )
    assert _fetch(repository, fresh_sending)[0] == "SENDING"

    published = repository._connection.execute(
        "SELECT status FROM publications "
        "WHERE product_id = 'A4'"
    ).fetchone()
    assert published[0] == "PUBLISHED"

    assert (
        repository.reconcile_stale_attempts(
            older_than=now - timedelta(seconds=600)
        )
        == 0
    )


def test_reconciliation_rows_do_not_block_cooldown(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    now = datetime(2026, 8, 15, 12, 0)

    attempt_id = repository.begin_attempt(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        attempted_at=now,
    )
    repository.mark_sending(attempt_id)
    repository.mark_unknown(attempt_id)

    assert repository.was_published("123") is False
    assert (
        repository.was_published_recently(
            "123", now=now
        )
        is False
    )
    # documents known behaviour: count() sees every status
    assert repository.count("123") == 1

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=now,
    )

    assert repository.was_published("123") is True
    assert (
        repository.was_published_recently(
            "123", now=now
        )
        is True
    )
    assert repository.count("123") == 2


def test_record_persists_message_id(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    now = datetime(2026, 8, 15, 12, 0)

    repository.record(
        product_id="123",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=now,
        message_id=42,
    )
    repository.record(
        product_id="456",
        affiliate_url="https://example.com",
        price=75.0,
        published_at=now,
    )

    with_id = repository._connection.execute(
        "SELECT message_id FROM publications "
        "WHERE product_id = '123'"
    ).fetchone()
    without_id = repository._connection.execute(
        "SELECT message_id FROM publications "
        "WHERE product_id = '456'"
    ).fetchone()

    assert with_id[0] == 42
    assert without_id[0] is None


def test_record_persists_image_url(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    repository.record(
        product_id="B0IMG2",
        affiliate_url="https://example.com",
        price=29.99,
        published_at=datetime(2026, 8, 15, 12, 0),
        image_url="https://images.example.com/razer.jpg",
    )

    row = repository._connection.execute(
        "SELECT image_url FROM publications "
        "WHERE product_id = 'B0IMG2'"
    ).fetchone()

    assert row[0] == "https://images.example.com/razer.jpg"


def test_fresh_pending_row_is_not_reconciled(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    now = datetime(2026, 8, 15, 12, 0)

    fresh_pending = repository.begin_attempt(
        product_id="P1",
        affiliate_url="https://example.com",
        price=10.0,
        attempted_at=now - timedelta(seconds=599),
    )

    resolved = repository.reconcile_stale_attempts(
        older_than=now - timedelta(seconds=600)
    )

    assert resolved == 0
    assert _fetch(repository, fresh_pending)[0] == "PENDING"

    stale_pending = repository.begin_attempt(
        product_id="P2",
        affiliate_url="https://example.com",
        price=10.0,
        attempted_at=now - timedelta(seconds=601),
    )

    resolved = repository.reconcile_stale_attempts(
        older_than=now - timedelta(seconds=600)
    )

    assert resolved == 1
    assert _fetch(repository, stale_pending)[0] == (
        "RECONCILIATION"
    )
    assert _fetch(repository, fresh_pending)[0] == "PENDING"

    repository.close()


def test_reconnect_reconciles_attempts_from_crashed_process(
    tmp_path,
):
    """A fresh process reconciles what a crashed run left behind.

    Two connections to the same file emulate the crash/restart
    boundary: the first instance dies with committed rows, the
    second one opens the database again (migrations are
    idempotent) and resolves only the stale rows.
    """
    db_path = str(tmp_path / "publication.db")
    now = datetime(2026, 8, 15, 12, 0)
    stale = now - timedelta(seconds=601)

    crashed = PublicationRepository(db_path)
    stale_pending = crashed.begin_attempt(
        product_id="A1",
        affiliate_url="https://example.com",
        price=10.0,
        attempted_at=stale,
    )
    stale_sending = crashed.begin_attempt(
        product_id="A2",
        affiliate_url="https://example.com",
        price=10.0,
        attempted_at=stale,
    )
    crashed.mark_sending(stale_sending)
    crashed.close()

    restarted = PublicationRepository(db_path)

    resolved = restarted.reconcile_stale_attempts(
        older_than=now - timedelta(seconds=600)
    )

    assert resolved == 2
    assert _fetch(restarted, stale_pending)[0] == (
        "RECONCILIATION"
    )
    assert _fetch(restarted, stale_sending)[0] == (
        "RECONCILIATION"
    )
    assert restarted.reconcile_stale_attempts(
        older_than=now - timedelta(seconds=600)
    ) == 0

    restarted.close()


def _begin_exclusive(repository, duplicate_check, product_id="123"):
    return repository.begin_attempt_exclusive(
        duplicate_check=duplicate_check,
        product_id=product_id,
        affiliate_url="https://example.com",
        price=75.0,
        attempted_at=datetime(2026, 8, 15, 12, 0),
    )


def test_begin_attempt_exclusive_inserts_when_check_is_clear(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    attempt_id = _begin_exclusive(
        repository,
        lambda: False,
    )

    status, published_at, message_id = _fetch(
        repository, attempt_id
    )

    assert isinstance(attempt_id, int)
    assert status == "PENDING"
    assert published_at == datetime(
        2026, 8, 15, 12, 0
    ).isoformat()
    assert message_id is None
    assert repository.count("123") == 1
    assert repository._connection.in_transaction is False


def test_begin_attempt_exclusive_returns_none_for_duplicates(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    assert (
        _begin_exclusive(repository, lambda: False) is not None
    )

    blocked = _begin_exclusive(repository, lambda: True)

    assert blocked is None
    assert repository.count("123") == 1
    assert repository._connection.in_transaction is False

    # the connection is usable again after the rejected check
    assert (
        _begin_exclusive(
            repository,
            lambda: False,
            product_id="456",
        )
        is not None
    )
    assert repository.count("456") == 1


def test_begin_attempt_exclusive_rolls_back_when_check_raises(
    tmp_path,
):
    import pytest

    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    def exploding_check():
        raise RuntimeError("duplicate check failed")

    with pytest.raises(RuntimeError):
        _begin_exclusive(repository, exploding_check)

    assert repository.count("123") == 0
    assert repository._connection.in_transaction is False

    assert (
        _begin_exclusive(repository, lambda: False) is not None
    )


def _seed_for_verification(
    repository,
    product_id,
    status,
    published_at,
    message_id=None,
):
    repository.record(
        product_id=product_id,
        affiliate_url=f"https://example.com/{product_id}",
        price=10.0,
        published_at=published_at,
        status=status,
        message_id=message_id,
    )


def test_attempts_for_verification_filters_and_orders(
    tmp_path,
):
    repository = PublicationRepository(
        str(tmp_path / "publication.db")
    )

    now = datetime(2026, 8, 15, 12, 0)
    stale_older = now - timedelta(seconds=700)
    stale_newer = now - timedelta(seconds=650)

    _seed_for_verification(
        repository, "OK1", "SENDING", stale_older, 42
    )
    _seed_for_verification(
        repository, "OK2", "RECONCILIATION", stale_newer, 43
    )
    _seed_for_verification(
        repository, "NOP", "SENDING", stale_older, None
    )
    _seed_for_verification(
        repository, "PEND", "PENDING", stale_older, 44
    )
    _seed_for_verification(
        repository, "PUB", "PUBLISHED", stale_older, 45
    )
    _seed_for_verification(
        repository,
        "FRESH",
        "SENDING",
        now - timedelta(seconds=599),
        46,
    )
    _seed_for_verification(
        repository,
        "OLD",
        "SENDING",
        now - timedelta(hours=49),
        47,
    )

    records = repository.attempts_for_verification(
        stale_before=now - timedelta(seconds=600),
        not_older_than=now - timedelta(hours=48),
        limit=10,
    )

    assert [
        record.product_id for record in records
    ] == ["OK1", "OK2"]
    assert [record.message_id for record in records] == [42, 43]
    assert records[0].published_at == stale_older
    assert records[0].affiliate_url == (
        "https://example.com/OK1"
    )

    limited = repository.attempts_for_verification(
        stale_before=now - timedelta(seconds=600),
        not_older_than=now - timedelta(hours=48),
        limit=1,
    )

    assert [
        record.product_id for record in limited
    ] == ["OK1"]
