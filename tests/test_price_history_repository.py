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
