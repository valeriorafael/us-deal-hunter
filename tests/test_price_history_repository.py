import sqlite3
from datetime import datetime, timedelta

import pytest

from app.models.price_history import PriceHistory
from app.services.price_history_repository import PriceHistoryRepository


def test_repository_saves_history(tmp_path):
    db = tmp_path / "test.db"
    repository = PriceHistoryRepository(str(db))

    item = PriceHistory(
        "123",
        75.0,
        recorded_at=datetime(2026, 8, 15),
    )

    repository.save(item)

    result = repository.get_by_product("123")

    assert result == [item]


def test_repository_separates_products(tmp_path):
    db = tmp_path / "test.db"
    repository = PriceHistoryRepository(str(db))

    first = PriceHistory(
        "123",
        75.0,
        recorded_at=datetime(2026, 8, 15),
    )

    second = PriceHistory(
        "999",
        50.0,
        recorded_at=datetime(2026, 8, 15),
    )

    repository.save(first)
    repository.save(second)

    assert repository.get_by_product("123") == [first]
    assert repository.get_by_product("999") == [second]


def test_repository_returns_history_in_chronological_order(tmp_path):
    db = tmp_path / "test.db"
    repository = PriceHistoryRepository(str(db))

    newest = PriceHistory(
        "123",
        70.0,
        recorded_at=datetime(2026, 8, 15),
    )

    oldest = PriceHistory(
        "123",
        100.0,
        recorded_at=datetime(2026, 8, 1),
    )

    middle = PriceHistory(
        "123",
        80.0,
        recorded_at=datetime(2026, 8, 10),
    )

    repository.save(newest)
    repository.save(oldest)
    repository.save(middle)

    assert repository.get_by_product("123") == [
        oldest,
        middle,
        newest,
    ]


def test_repository_count(tmp_path):
    db = tmp_path / "test.db"
    repository = PriceHistoryRepository(str(db))

    repository.save(
        PriceHistory(
            "123",
            100.0,
            recorded_at=datetime(2026, 8, 15),
        )
    )

    repository.save(
        PriceHistory(
            "123",
            90.0,
            recorded_at=datetime(2026, 8, 14),
        )
    )

    repository.save(
        PriceHistory(
            "999",
            50.0,
            recorded_at=datetime(2026, 8, 15),
        )
    )

    assert repository.count("123") == 2
    assert repository.count("999") == 1
    assert repository.count("does-not-exist") == 0


def test_repository_persists_between_instances(tmp_path):
    db = tmp_path / "test.db"

    first_repository = PriceHistoryRepository(str(db))

    item = PriceHistory(
        "123",
        75.0,
        recorded_at=datetime(2026, 8, 15),
    )

    first_repository.save(item)

    second_repository = PriceHistoryRepository(str(db))

    result = second_repository.get_by_product("123")

    assert result == [item]


def test_repository_persists_between_instances(tmp_path):
    db_path = str(tmp_path / "persistent.db")

    first_repository = PriceHistoryRepository(db_path)

    item = PriceHistory(
        "123",
        75.0,
        recorded_at=datetime(2026, 8, 15),
    )

    first_repository.save(item)

    second_repository = PriceHistoryRepository(db_path)

    result = second_repository.get_by_product("123")

    assert result == [item]


def test_delete_older_than_removes_only_expired_entries(
    tmp_path,
):
    repository = PriceHistoryRepository(
        str(tmp_path / "prune.db")
    )

    now = datetime(2026, 8, 15)

    old = PriceHistory(
        "123",
        100.0,
        recorded_at=now - timedelta(days=120),
    )

    boundary = PriceHistory(
        "123",
        95.0,
        recorded_at=now - timedelta(days=90),
    )

    recent = PriceHistory(
        "123",
        70.0,
        recorded_at=now - timedelta(days=10),
    )

    for item in (old, boundary, recent):
        repository.save(item)

    removed = repository.delete_older_than(
        now - timedelta(days=90)
    )

    assert removed == 1
    assert repository.get_by_product("123") == [
        boundary,
        recent,
    ]


def test_delete_older_than_keeps_entire_window(
    tmp_path,
):
    repository = PriceHistoryRepository(
        str(tmp_path / "window.db")
    )

    now = datetime(2026, 8, 15)

    entries = [
        PriceHistory(
            "123",
            100.0 - index,
            recorded_at=now - timedelta(days=index),
        )
        for index in range(0, 90)
    ]

    for item in entries:
        repository.save(item)

    removed = repository.delete_older_than(
        now - timedelta(days=90)
    )

    assert removed == 0
    assert len(repository.get_by_product("123")) == 90


def test_delete_older_than_prunes_every_product(
    tmp_path,
):
    repository = PriceHistoryRepository(
        str(tmp_path / "multi.db")
    )

    now = datetime(2026, 8, 15)

    old = PriceHistory(
        "123",
        100.0,
        recorded_at=now - timedelta(days=200),
    )

    other = PriceHistory(
        "999",
        50.0,
        recorded_at=now - timedelta(days=200),
    )

    repository.save(old)
    repository.save(other)

    removed = repository.delete_older_than(
        now - timedelta(days=90)
    )

    assert removed == 2
    assert repository.get_by_product("123") == []
    assert repository.get_by_product("999") == []


def test_delete_older_than_on_empty_history(tmp_path):
    repository = PriceHistoryRepository(
        str(tmp_path / "empty.db")
    )

    removed = repository.delete_older_than(
        datetime(2026, 8, 15) - timedelta(days=90)
    )

    assert removed == 0


def test_history_index_is_created(tmp_path):
    import sqlite3

    db_path = str(tmp_path / "indexed.db")

    PriceHistoryRepository(db_path)

    connection = sqlite3.connect(db_path)

    indexes = [
        row[1]
        for row in connection.execute(
            "PRAGMA index_list('price_history')"
        )
    ]

    connection.close()

    assert "idx_price_history_product_recorded" in indexes


def test_get_by_product_uses_the_composite_index(tmp_path):
    db_path = str(tmp_path / "plan.db")

    repository = PriceHistoryRepository(db_path)

    now = datetime(2026, 8, 15)

    for index in range(200):
        repository.save(
            PriceHistory(
                "123",
                100.0,
                recorded_at=now - timedelta(days=index),
            )
        )

    plan = repository._connection.execute(
        "EXPLAIN QUERY PLAN "
        "SELECT * FROM price_history "
        "WHERE product_id = ? ORDER BY recorded_at ASC",
        ("123",),
    ).fetchall()

    detail = " ".join(row[-1] for row in plan)

    assert "SCAN price_history" not in detail
    assert "USING INDEX" in detail


def test_count_older_than(tmp_path):
    repository = PriceHistoryRepository(
        str(tmp_path / "count.db")
    )

    now = datetime(2026, 8, 15)

    entries = [
        PriceHistory(
            "123",
            100.0,
            recorded_at=now - timedelta(days=days),
        )
        for days in (200, 91, 90, 45, 0)
    ]

    for item in entries:
        repository.save(item)

    assert repository.count_older_than(
        now - timedelta(days=90)
    ) == 2
    assert repository.count_older_than(
        now + timedelta(days=1)
    ) == 5


def test_prune_older_than_backs_up_before_deleting(tmp_path):

    repository = PriceHistoryRepository(
        str(tmp_path / "backup.db")
    )

    now = datetime(2026, 8, 15)

    old = PriceHistory(
        "123",
        100.0,
        recorded_at=now - timedelta(days=200),
    )

    recent = PriceHistory(
        "123",
        70.0,
        recorded_at=now - timedelta(days=10),
    )

    repository.save(old)
    repository.save(recent)

    removed = repository.prune_older_than(
        now - timedelta(days=90)
    )

    backups = sorted(
        (tmp_path / "backups").glob("backup-*.db")
    )

    assert removed == 1
    # one backup from the baseline migration plus the copy
    # taken immediately before the prune
    assert len(backups) == 2

    restored = sqlite3.connect(str(backups[-1]))

    count = restored.execute(
        "SELECT COUNT(*) FROM price_history"
    ).fetchone()[0]

    restored.close()

    assert count == 2
    assert repository.get_by_product("123") == [recent]


def test_save_updates_the_entry_of_the_same_day(tmp_path):
    repository = PriceHistoryRepository(
        str(tmp_path / "upsert.db")
    )

    first = PriceHistory(
        "123",
        100.0,
        recorded_at=datetime(2026, 8, 15, 10, 0),
    )

    second = PriceHistory(
        "123",
        95.0,
        recorded_at=datetime(2026, 8, 15, 18, 0),
    )

    repository.save(first)
    repository.save(second)

    assert repository.count("123") == 1
    assert repository.get_by_product("123") == [second]


def test_save_keeps_entries_of_other_days(tmp_path):
    repository = PriceHistoryRepository(
        str(tmp_path / "days.db")
    )

    first = PriceHistory(
        "123",
        100.0,
        recorded_at=datetime(2026, 8, 15, 10, 0),
    )

    second = PriceHistory(
        "123",
        95.0,
        recorded_at=datetime(2026, 8, 16, 10, 0),
    )

    repository.save(first)
    repository.save(second)

    assert repository.get_by_product("123") == [
        first,
        second,
    ]


def test_price_history_rejects_duplicate_days(tmp_path):
    repository = PriceHistoryRepository(
        str(tmp_path / "unique.db")
    )

    repository.save(
        PriceHistory(
            "123",
            100.0,
            recorded_at=datetime(2026, 8, 15, 10, 0),
        )
    )

    with pytest.raises(sqlite3.IntegrityError):
        repository._connection.execute(
            """
            INSERT INTO price_history (
                product_id,
                price,
                currency,
                recorded_at
            )
            VALUES (?, ?, ?, ?)
            """,
            ("123", 90.0, "USD", "2026-08-15T20:00:00"),
        )

    assert repository.count("123") == 1


def test_repository_closes_connection_as_context_manager(tmp_path):
    db_path = tmp_path / "context.db"

    with PriceHistoryRepository(str(db_path)) as repository:
        repository.save(
            PriceHistory(
                "123",
                100.0,
                recorded_at=datetime(2026, 8, 15, 10, 0),
            )
        )

        assert repository.count("123") == 1
        assert (
            repository._connection.execute(
                "PRAGMA journal_mode"
            ).fetchone()[0]
            == "wal"
        )

    with pytest.raises(sqlite3.ProgrammingError):
        repository.count("123")

    repository.close()

    assert not db_path.with_name(
        f"{db_path.name}-wal"
    ).exists()
    assert not db_path.with_name(
        f"{db_path.name}-shm"
    ).exists()


def test_repository_close_supports_memory_database():
    with PriceHistoryRepository(":memory:") as repository:
        repository.save(
            PriceHistory(
                "123",
                100.0,
                recorded_at=datetime(2026, 8, 15, 10, 0),
            )
        )

        assert repository.count("123") == 1

    with pytest.raises(sqlite3.ProgrammingError):
        repository.count("123")
