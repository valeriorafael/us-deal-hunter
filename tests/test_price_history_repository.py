from datetime import datetime, timedelta

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
