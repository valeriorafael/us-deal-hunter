import logging
import sqlite3
from datetime import datetime

import pytest

from app.services import database
from app.services.database import connect


class _UnhealthyConnection:
    def execute(self, statement):
        class Cursor:
            def fetchone(self):
                return ("database disk image is malformed",)

        return Cursor()


def _query_plan(connection, query: str, params=()) -> str:
    rows = connection.execute(
        f"EXPLAIN QUERY PLAN {query}",
        params,
    ).fetchall()

    return " | ".join(str(row[-1]) for row in rows)


def test_connect_applies_pragmas(tmp_path):
    connection = connect(str(tmp_path / "pragmas.db"))

    assert (
        connection.execute("PRAGMA foreign_keys").fetchone()[0]
        == 1
    )
    assert (
        connection.execute("PRAGMA busy_timeout").fetchone()[0]
        == 5000
    )
    assert (
        connection.execute("PRAGMA journal_mode").fetchone()[0]
        == "wal"
    )

    connection.close()


def test_wal_mode_is_persistent_after_reopen(tmp_path):
    db_path = str(tmp_path / "persistent_wal.db")

    connect(db_path).close()

    reopened = connect(db_path)

    assert (
        reopened.execute("PRAGMA journal_mode").fetchone()[0]
        == "wal"
    )

    reopened.close()


def test_connect_memory_database_uses_memory_journal():
    connection = connect(":memory:")

    assert (
        connection.execute("PRAGMA journal_mode").fetchone()[0]
        == "memory"
    )
    assert (
        connection.execute("PRAGMA foreign_keys").fetchone()[0]
        == 1
    )
    assert (
        connection.execute("PRAGMA busy_timeout").fetchone()[0]
        == 5000
    )

    connection.close()


def test_apply_pragmas_keeps_current_mode_when_wal_fails(
    caplog,
):
    class FailingConnection:
        def execute(self, statement):
            if statement.startswith("PRAGMA journal_mode"):
                raise sqlite3.OperationalError(
                    "disk I/O error"
                )

            return None

    with caplog.at_level(logging.WARNING):
        mode = database.apply_pragmas(
            FailingConnection(),
            "data/example.db",
        )

    assert mode is None
    assert "data/example.db" in caplog.text
    assert "disk I/O error" in caplog.text


def test_apply_pragmas_normalizes_corrupt_database_error():
    class CorruptedConnection:
        def execute(self, statement):
            if statement.startswith("PRAGMA journal_mode"):
                raise sqlite3.DatabaseError(
                    "database disk image is malformed"
                )

            return None

    with pytest.raises(database.DatabaseBackupError) as excinfo:
        database.apply_pragmas(
            CorruptedConnection(),
            "data/example.db",
        )

    assert "data/example.db" in str(excinfo.value)
    assert isinstance(
        excinfo.value.__cause__,
        sqlite3.DatabaseError,
    )
    assert "malformed" in str(excinfo.value.__cause__)


def test_apply_pragmas_accepts_memory_journal_without_warning(
    caplog,
):
    connection = sqlite3.connect(":memory:")

    with caplog.at_level(logging.WARNING):
        mode = database.apply_pragmas(connection, ":memory:")

    assert mode == "memory"
    assert caplog.text == ""


def test_migrations_set_user_version_to_latest(tmp_path):
    connection = connect(str(tmp_path / "versioned.db"))

    assert (
        connection.execute("PRAGMA user_version").fetchone()[0]
        == database.LATEST_SCHEMA_VERSION
    )

    connection.close()


def test_migration_2_creates_publication_indexes(tmp_path):
    connection = connect(str(tmp_path / "pub_indexes.db"))

    indexes = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' "
            "AND name LIKE 'idx_publications_%'"
        )
    }

    assert indexes == {
        "idx_publications_channel_product_published",
        "idx_publications_product_published",
        "idx_publications_published_at",
        "idx_publications_status",
    }

    connection.close()


def test_publication_queries_use_indexes(tmp_path):
    connection = connect(str(tmp_path / "query_plan.db"))

    cooldown_plan = _query_plan(
        connection,
        """
        SELECT published_at
        FROM publications
        WHERE channel = ?
          AND product_id = ?
          AND status = 'PUBLISHED'
        ORDER BY published_at DESC
        LIMIT 1
        """,
        ("TELEGRAM", "B00001"),
    )

    status_plan = _query_plan(
        connection,
        """
        SELECT COUNT(*)
        FROM publications
        WHERE status = 'PUBLISHED'
        """,
    )

    assert "INDEX" in cooldown_plan
    assert (
        "idx_publications_channel_product_published"
        in cooldown_plan
    )
    assert "SCAN publications" not in cooldown_plan
    assert "INDEX" in status_plan
    assert "idx_publications_status" in status_plan
    assert "SCAN publications" not in status_plan

    connection.close()


def test_migrations_create_baseline_tables(tmp_path):
    connection = connect(str(tmp_path / "baseline.db"))

    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' "
            "AND name IN ('price_history', 'publications')"
        )
    ]

    indexes = [
        row[1]
        for row in connection.execute(
            "PRAGMA index_list('price_history')"
        )
    ]

    assert sorted(tables) == ["price_history", "publications"]
    assert (
        "idx_price_history_product_recorded" in indexes
    )

    connection.close()


def test_migrations_are_not_reapplied_on_reopen(tmp_path):
    db_path = str(tmp_path / "reopen.db")

    first = connect(db_path)

    version = first.execute(
        "PRAGMA user_version"
    ).fetchone()[0]
    objects = first.execute(
        "SELECT COUNT(*) FROM sqlite_master"
    ).fetchone()[0]

    first.close()

    reopened = connect(db_path)

    assert (
        reopened.execute("PRAGMA user_version").fetchone()[0]
        == version
    )
    assert (
        reopened.execute(
            "SELECT COUNT(*) FROM sqlite_master"
        ).fetchone()[0]
        == objects
    )

    reopened.close()


def test_migration_baseline_adopts_legacy_publications_table(
    tmp_path,
):
    db_path = str(tmp_path / "legacy.db")

    legacy = sqlite3.connect(db_path)
    legacy.execute(
        """
        CREATE TABLE publications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            affiliate_url TEXT NOT NULL,
            price REAL NOT NULL,
            published_at TEXT NOT NULL
        )
        """
    )
    legacy.commit()
    legacy.close()

    migrated = connect(db_path)

    columns = [
        row[1]
        for row in migrated.execute(
            "PRAGMA table_info(publications)"
        )
    ]

    defaults = {
        row[1]: row[4]
        for row in migrated.execute(
            "PRAGMA table_info(publications)"
        )
    }

    assert columns == [
        "id",
        "product_id",
        "affiliate_url",
        "price",
        "published_at",
        "title",
        "score",
        "label",
        "discount_vs_30d",
        "source_query",
        "status",
        "message_id",
        "channel",
    ]
    assert defaults["status"] == "'PUBLISHED'"
    assert (
        migrated.execute("PRAGMA user_version").fetchone()[0]
        == database.LATEST_SCHEMA_VERSION
    )

    migrated.close()

    reopened = connect(db_path)

    assert [
        row[1]
        for row in reopened.execute(
            "PRAGMA table_info(publications)"
        )
    ] == columns

    reopened.close()


def test_migrations_reject_newer_schema_version(tmp_path):
    db_path = str(tmp_path / "future.db")

    future = sqlite3.connect(db_path)
    future.execute("PRAGMA user_version = 99")
    future.commit()
    future.close()

    with pytest.raises(
        database.UnsupportedSchemaVersionError
    ) as excinfo:
        connect(db_path)

    assert "99" in str(excinfo.value)


def _create_legacy_history(db_path, rows):
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            price REAL NOT NULL,
            currency TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        )
        """
    )
    # a realistic pre-v3 database also carries the v1
    # baseline publications table
    connection.execute(
        """
        CREATE TABLE publications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            affiliate_url TEXT NOT NULL,
            price REAL NOT NULL,
            published_at TEXT NOT NULL,
            title TEXT,
            score REAL,
            label TEXT,
            discount_vs_30d REAL,
            source_query TEXT,
            status TEXT NOT NULL DEFAULT 'PUBLISHED'
        )
        """
    )
    connection.executemany(
        """
        INSERT INTO price_history (
            product_id,
            price,
            currency,
            recorded_at
        )
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    connection.execute("PRAGMA user_version = 2")
    connection.commit()
    connection.close()


def test_migrations_are_complete_and_ordered():
    versions = [
        migration.version for migration in database.MIGRATIONS
    ]

    assert versions == sorted(set(versions))
    assert versions == [1, 2, 3, 4, 5]
    assert database.LATEST_SCHEMA_VERSION == 5
    assert database.LATEST_SCHEMA_VERSION == max(versions)


def test_migration_3_deduplicates_before_unique_index(
    tmp_path,
):
    db_path = str(tmp_path / "legacy_history.db")

    _create_legacy_history(
        db_path,
        [
            (
                "B00001",
                100.0,
                "USD",
                "2026-08-15T10:00:00",
            ),
            (
                "B00001",
                95.0,
                "USD",
                "2026-08-15T18:00:00",
            ),
            (
                "B00001",
                90.0,
                "USD",
                "2026-08-16T10:00:00",
            ),
        ],
    )

    migrated = connect(db_path)

    rows = migrated.execute(
        """
        SELECT price, recorded_at
        FROM price_history
        ORDER BY recorded_at
        """
    ).fetchall()

    indexes = {
        row[0]
        for row in migrated.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index'"
        )
    }

    backups = list(
        database.backups_directory(db_path).glob(
            "legacy_history-*.db"
        )
    )

    assert (
        migrated.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        == database.LATEST_SCHEMA_VERSION
    )
    assert rows == [
        (95.0, "2026-08-15T18:00:00"),
        (90.0, "2026-08-16T10:00:00"),
    ]
    assert "ux_price_history_product_day" in indexes
    assert len(backups) == 1

    restored = sqlite3.connect(str(backups[0]))

    count = restored.execute(
        "SELECT COUNT(*) FROM price_history"
    ).fetchone()[0]

    restored.close()

    assert count == 3

    migrated.close()


def test_migration_failure_is_rolled_back(
    tmp_path,
    monkeypatch,
):
    db_path = str(tmp_path / "rollback.db")

    connect(db_path).close()

    broken = database.MIGRATIONS + (
        database.Migration(
            version=database.LATEST_SCHEMA_VERSION + 1,
            name="broken_migration",
            statements=(
                """
                CREATE TABLE IF NOT EXISTS rollback_probe (
                    id INTEGER PRIMARY KEY
                )
                """,
                "THIS IS NOT VALID SQL",
            ),
        ),
    )

    monkeypatch.setattr(database, "MIGRATIONS", broken)

    with pytest.raises(sqlite3.OperationalError):
        connect(db_path)

    connection = sqlite3.connect(db_path)

    version = connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0]

    probes = connection.execute(
        "SELECT COUNT(*) FROM sqlite_master "
        "WHERE name = 'rollback_probe'"
    ).fetchone()[0]

    connection.close()

    assert version == database.LATEST_SCHEMA_VERSION
    assert probes == 0


def test_backup_database_creates_timestamped_copy(tmp_path):
    db_path = str(tmp_path / "deal_hunter.db")

    connection = connect(db_path)
    connection.execute(
        """
        INSERT INTO price_history
            (product_id, price, currency, recorded_at)
        VALUES (?, ?, ?, ?)
        """,
        ("B00001", 10.5, "USD", "2026-10-01T00:00:00"),
    )
    connection.commit()

    target = database.backup_database(connection, db_path)

    connection.close()

    assert target is not None
    assert target.parent == database.backups_directory(db_path)
    assert target.name.startswith("deal_hunter-")
    assert target.name.endswith(".db")

    stamp = target.stem.removeprefix("deal_hunter-")
    datetime.strptime(stamp[:15], "%Y%m%d-%H%M%S")

    sequence = stamp[16:]
    assert len(sequence) == 6
    assert sequence.isdigit()

    restored = sqlite3.connect(str(target))

    row = restored.execute(
        "SELECT product_id, price FROM price_history"
    ).fetchone()

    restored.close()

    assert row == ("B00001", 10.5)


def test_backup_database_prunes_old_backups(tmp_path):
    db_path = str(tmp_path / "deal_hunter.db")

    connect(db_path).close()

    backups_dir = database.backups_directory(db_path)
    backups_dir.mkdir(parents=True, exist_ok=True)

    for day in range(1, 10):
        name = f"deal_hunter-2020010{day}-000000.db"

        (backups_dir / name).touch()

    database.prune_old_backup_files(db_path)

    names = {path.name for path in backups_dir.glob("*.db")}

    assert len(names) == database.BACKUP_RETENTION
    assert "deal_hunter-20200101-000000.db" not in names
    assert "deal_hunter-20200102-000000.db" not in names
    assert "deal_hunter-20200103-000000.db" not in names
    assert "deal_hunter-20200104-000000.db" in names
    assert "deal_hunter-20200109-000000.db" in names


def test_backup_database_refuses_unhealthy_database(tmp_path):
    db_path = str(tmp_path / "broken.db")

    with pytest.raises(database.DatabaseBackupError) as excinfo:
        database.backup_database(
            _UnhealthyConnection(),
            db_path,
        )

    assert "malformed" in str(excinfo.value)
    assert not database.backups_directory(db_path).exists()


def test_backup_converts_corrupt_database_error(tmp_path):
    db_path = str(tmp_path / "broken.db")

    with pytest.raises(database.DatabaseBackupError) as excinfo:
        database.backup_database(
            _CorruptedConnection(),
            db_path,
        )

    assert "broken.db" in str(excinfo.value)
    assert isinstance(
        excinfo.value.__cause__,
        sqlite3.DatabaseError,
    )
    assert "malformed" in str(excinfo.value.__cause__)
    assert not database.backups_directory(db_path).exists()


class _FixedDateTime:
    @classmethod
    def now(cls):
        return datetime(2026, 10, 1, 12, 0, 0)


class _CorruptedConnection:
    def execute(self, statement):
        raise sqlite3.DatabaseError(
            "database disk image is malformed"
        )


class _FailingBackupConnection:
    def execute(self, statement):
        class Cursor:
            def fetchone(self):
                return ("ok",)

        return Cursor()

    def commit(self):
        return None

    def backup(self, target):
        raise sqlite3.OperationalError("disk I/O error")


class _BrokenCommitConnection:
    def execute(self, statement):
        class Cursor:
            def fetchone(self):
                return ("ok",)

        return Cursor()

    def commit(self):
        raise sqlite3.ProgrammingError(
            "Cannot operate on a closed database."
        )


def test_backup_same_second_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "datetime", _FixedDateTime)

    db_path = str(tmp_path / "deal_hunter.db")
    connection = connect(db_path)

    backups_dir = database.backups_directory(db_path)
    existing_backups = len(
        list(backups_dir.glob("*.db"))
    )

    connection.execute(
        """
        INSERT INTO price_history
            (product_id, price, currency, recorded_at)
        VALUES (?, ?, ?, ?)
        """,
        ("B00001", 10.5, "USD", "2026-10-01T00:00:00"),
    )
    connection.commit()

    first = database.backup_database(connection, db_path)

    connection.execute("DELETE FROM price_history")
    connection.commit()

    second = database.backup_database(connection, db_path)

    names = sorted(path.name for path in backups_dir.glob("*.db"))

    assert first is not None and second is not None
    assert first != second
    assert first.name.startswith(
        "deal_hunter-20261001-120000-"
    )
    assert second.name.startswith(
        "deal_hunter-20261001-120000-"
    )
    assert len(names) == existing_backups + 2
    assert list(backups_dir.glob("*.part")) == []

    restored = sqlite3.connect(str(first))

    rows = restored.execute(
        "SELECT product_id FROM price_history"
    ).fetchall()

    restored.close()

    assert rows == [("B00001",)]

    connection.close()


def test_backup_failure_removes_partial_file(tmp_path):
    db_path = str(tmp_path / "deal_hunter.db")
    connection = _FailingBackupConnection()

    with pytest.raises(database.DatabaseBackupError) as excinfo:
        database.backup_database(connection, db_path)

    assert "disk I/O error" in str(excinfo.value)

    backups_dir = database.backups_directory(db_path)

    assert list(backups_dir.glob("*.db")) == []
    assert list(backups_dir.glob("*.part")) == []


def test_backup_rejects_invalid_copy(tmp_path, monkeypatch):
    db_path = str(tmp_path / "deal_hunter.db")
    connection = sqlite3.connect(db_path)

    def write_invalid_copy(source, part_path):
        part_path.write_bytes(b"this is not a database")

    monkeypatch.setattr(
        database,
        "_write_backup",
        write_invalid_copy,
    )

    with pytest.raises(database.DatabaseBackupError):
        database.backup_database(connection, db_path)

    backups_dir = database.backups_directory(db_path)

    assert list(backups_dir.glob("*.db")) == []
    assert list(backups_dir.glob("*.part")) == []

    connection.close()


def test_backup_converts_filesystem_error(tmp_path):
    db_path = str(tmp_path / "deal_hunter.db")
    connection = sqlite3.connect(db_path)

    (tmp_path / "backups").write_text("not a directory")

    with pytest.raises(database.DatabaseBackupError) as excinfo:
        database.backup_database(connection, db_path)

    assert "deal_hunter.db" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, OSError)

    connection.close()


def test_backup_preserves_programming_errors(tmp_path):
    db_path = str(tmp_path / "deal_hunter.db")
    connection = _BrokenCommitConnection()

    with pytest.raises(sqlite3.ProgrammingError):
        database.backup_database(connection, db_path)

    backups_dir = database.backups_directory(db_path)

    assert list(backups_dir.glob("*")) == []


def test_connect_closes_connection_when_migration_fails(
    tmp_path,
    monkeypatch,
):
    db_path = str(tmp_path / "rollback_close.db")

    broken = database.MIGRATIONS + (
        database.Migration(
            version=database.LATEST_SCHEMA_VERSION + 1,
            name="broken_migration",
            statements=("THIS IS NOT VALID SQL",),
        ),
    )

    monkeypatch.setattr(database, "MIGRATIONS", broken)

    with pytest.raises(sqlite3.OperationalError):
        connect(db_path)

    assert not tmp_path.joinpath(
        "rollback_close.db-wal"
    ).exists()
    assert not tmp_path.joinpath(
        "rollback_close.db-shm"
    ).exists()


def _make_v3_database(db_path, monkeypatch, publications=()):
    original = database.MIGRATIONS

    monkeypatch.setattr(
        database,
        "MIGRATIONS",
        tuple(
            migration
            for migration in original
            if migration.version <= 3
        ),
    )

    connection = connect(db_path)

    for publication in publications:
        connection.execute(
            """
            INSERT INTO publications (
                product_id,
                affiliate_url,
                price,
                published_at,
                status
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            publication,
        )

    connection.commit()
    connection.close()

    monkeypatch.setattr(database, "MIGRATIONS", original)


def test_migration_4_adds_message_id_column(tmp_path):
    db_path = str(tmp_path / "fresh.db")

    connection = connect(db_path)

    columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(publications)"
        ).fetchall()
    }
    version = connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0]
    connection.close()

    assert "message_id" in columns
    assert version == database.LATEST_SCHEMA_VERSION == 5


def test_migration_4_preserves_existing_publication_rows(
    tmp_path,
    monkeypatch,
):
    db_path = str(tmp_path / "legacy_publications.db")

    _make_v3_database(
        db_path,
        monkeypatch,
        publications=[
            (
                "B00001",
                "https://example.com/dp/B00001",
                99.5,
                "2026-08-15T12:00:00",
                "PUBLISHED",
            )
        ],
    )

    connection = connect(db_path)

    rows = connection.execute(
        """
        SELECT product_id, price, status, message_id
        FROM publications
        """
    ).fetchall()
    version = connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0]
    connection.close()

    assert rows == [
        ("B00001", 99.5, "PUBLISHED", None)
    ]
    assert version == 5


def test_migration_4_is_idempotent_on_reopen(tmp_path):
    db_path = str(tmp_path / "reopen.db")

    first = connect(db_path)
    first.close()

    second = connect(db_path)

    message_id_columns = [
        row
        for row in second.execute(
            "PRAGMA table_info(publications)"
        ).fetchall()
        if row[1] == "message_id"
    ]
    version = second.execute(
        "PRAGMA user_version"
    ).fetchone()[0]
    second.close()

    assert len(message_id_columns) == 1
    assert version == 5


def test_migration_4_creates_no_new_backup(
    tmp_path,
    monkeypatch,
):
    db_path = str(tmp_path / "no_backup.db")
    _make_v3_database(db_path, monkeypatch)

    backups_dir = database.backups_directory(db_path)
    before = (
        len(list(backups_dir.glob("*.db")))
        if backups_dir.exists()
        else 0
    )

    connection = connect(db_path)
    connection.close()

    after = (
        len(list(backups_dir.glob("*.db")))
        if backups_dir.exists()
        else 0
    )

    assert after == before


def test_migrations_reject_version_six(tmp_path):
    db_path = str(tmp_path / "future6.db")

    future = sqlite3.connect(db_path)
    future.execute("PRAGMA user_version = 6")
    future.commit()
    future.close()

    with pytest.raises(
        database.UnsupportedSchemaVersionError
    ) as excinfo:
        connect(db_path)

    assert "6" in str(excinfo.value)


def test_migration_rollback_failure_does_not_mask_original_error(
    tmp_path,
    caplog,
):
    db_path = str(tmp_path / "rollback_fail.db")

    connect(db_path).close()

    broken = database.Migration(
        version=database.LATEST_SCHEMA_VERSION + 1,
        name="broken_migration",
        statements=("THIS IS NOT VALID SQL",),
    )

    class RollbackFailConnection:
        def __init__(self, real):
            self._real = real

        def execute(self, statement, *args):
            if statement.strip().upper() == "ROLLBACK":
                raise sqlite3.OperationalError(
                    "rollback exploded"
                )

            return self._real.execute(statement, *args)

        def __getattr__(self, name):
            return getattr(self._real, name)

    real = sqlite3.connect(db_path)
    wrapped = RollbackFailConnection(real)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(
            sqlite3.OperationalError,
        ) as exc_info:
            database._apply_migration(
                wrapped,
                broken,
            )

    original = str(exc_info.value)

    assert "rollback exploded" not in original
    assert "syntax error" in original
    assert any(
        "rollback failed for migration" in record.getMessage()
        for record in caplog.records
    )

    real.close()
