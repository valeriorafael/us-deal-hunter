import itertools
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

BACKUP_RETENTION = 7

BACKUP_PART_SUFFIX = ".part"


class UnsupportedSchemaVersionError(RuntimeError):
    pass


class DatabaseBackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]
    requires_backup: bool = False
    adopt_legacy: bool = False


LEGACY_PUBLICATION_COLUMNS = {
    "title": (
        "ALTER TABLE publications ADD COLUMN title TEXT"
    ),
    "score": (
        "ALTER TABLE publications ADD COLUMN score REAL"
    ),
    "label": (
        "ALTER TABLE publications ADD COLUMN label TEXT"
    ),
    "discount_vs_30d": (
        "ALTER TABLE publications "
        "ADD COLUMN discount_vs_30d REAL"
    ),
    "source_query": (
        "ALTER TABLE publications "
        "ADD COLUMN source_query TEXT"
    ),
    "status": (
        "ALTER TABLE publications "
        "ADD COLUMN status TEXT NOT NULL DEFAULT 'PUBLISHED'"
    ),
}

MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="baseline_schema",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                price REAL NOT NULL,
                currency TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS publications (
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
            """,
            """
            CREATE INDEX IF NOT EXISTS
                idx_price_history_product_recorded
            ON price_history (product_id, recorded_at)
            """,
        ),
        adopt_legacy=True,
    ),
    Migration(
        version=2,
        name="publication_indexes",
        statements=(
            """
            CREATE INDEX IF NOT EXISTS
                idx_publications_product_published
            ON publications (product_id, published_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS
                idx_publications_published_at
            ON publications (published_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS
                idx_publications_status
            ON publications (status)
            """,
        ),
    ),
    Migration(
        version=3,
        name="price_history_unique_per_day",
        statements=(
            """
            DELETE FROM price_history
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM price_history
                GROUP BY
                    product_id,
                    substr(recorded_at, 1, 10)
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                ux_price_history_product_day
            ON price_history (
                product_id,
                substr(recorded_at, 1, 10)
            )
            """,
        ),
        requires_backup=True,
    ),
    Migration(
        version=4,
        name="publication_attempt_state",
        statements=(
            """
            ALTER TABLE publications
            ADD COLUMN message_id INTEGER
            """,
        ),
        requires_backup=False,
        adopt_legacy=False,
    ),
)

LATEST_SCHEMA_VERSION = max(
    migration.version for migration in MIGRATIONS
)


def connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)

    try:
        apply_pragmas(connection, db_path)
        run_migrations(connection, db_path)
    except BaseException:
        connection.close()

        raise

    return connection


def apply_pragmas(
    connection: sqlite3.Connection,
    db_path: str,
) -> str | None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")

    try:
        mode = connection.execute(
            "PRAGMA journal_mode = WAL"
        ).fetchone()[0]
    except sqlite3.OperationalError as exc:
        logger.warning(
            "WAL is unavailable for %s (%s); "
            "keeping the current journal mode.",
            db_path,
            exc,
        )

        return None
    except sqlite3.DatabaseError as exc:
        raise DatabaseBackupError(
            f"Cannot apply pragmas to {db_path}: {exc}"
        ) from exc

    if mode != "wal" and db_path != ":memory:":
        logger.warning(
            "WAL is unavailable for %s (journal_mode=%r); "
            "keeping the current journal mode.",
            db_path,
            mode,
        )

    return mode


def run_migrations(
    connection: sqlite3.Connection,
    db_path: str,
) -> None:
    current = connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0]

    if current > LATEST_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"Database schema version {current} is newer than "
            f"the supported version {LATEST_SCHEMA_VERSION}."
        )

    for migration in MIGRATIONS:
        if migration.version <= current:
            continue

        if migration.requires_backup and db_path != ":memory:":
            backup_database(connection, db_path)

        _apply_migration(connection, migration)


def backup_database(
    connection: sqlite3.Connection,
    db_path: str,
) -> Path | None:
    if db_path == ":memory:":
        return None

    backups_dir = backups_directory(db_path)
    part_path: Path | None = None
    target_path: Path | None = None
    completed = False

    try:
        _assert_database_is_healthy(connection, db_path)

        backups_dir.mkdir(parents=True, exist_ok=True)

        part_path, target_path = _reserve_backup_paths(
            backups_dir,
            db_path,
        )

        connection.commit()

        _write_backup(connection, part_path)
        _validate_backup(part_path, db_path)

        os.replace(part_path, target_path)

        completed = True
    except (sqlite3.ProgrammingError, sqlite3.InterfaceError):
        raise
    except DatabaseBackupError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise DatabaseBackupError(
            f"Backup of {db_path} failed: {exc}"
        ) from exc
    finally:
        if not completed:
            _discard_backup(part_path)

    try:
        prune_old_backup_files(db_path)
    except (sqlite3.ProgrammingError, sqlite3.InterfaceError):
        raise
    except (OSError, sqlite3.Error) as exc:
        raise DatabaseBackupError(
            f"Backup retention pruning failed for {db_path}: {exc}"
        ) from exc

    logger.info("database backup created: %s", target_path)

    return target_path


def backups_directory(db_path: str) -> Path:
    return Path(db_path).resolve().parent / "backups"


def backup_filename(db_path: str, sequence: int = 0) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    return f"{Path(db_path).stem}-{stamp}-{sequence:06d}.db"


def _reserve_backup_paths(
    backups_dir: Path,
    db_path: str,
) -> tuple[Path, Path]:
    """Reserve a unique backup name for this exact moment.

    The staging file is created with O_EXCL, so neither a second
    call in the same second nor another process can claim the
    same backup name. An existing backup file is never reused.
    """

    for sequence in itertools.count():
        target_path = backups_dir / backup_filename(
            db_path,
            sequence,
        )
        part_path = backups_dir / (
            f"{target_path.name}{BACKUP_PART_SUFFIX}"
        )

        if target_path.exists():
            continue

        try:
            descriptor = os.open(
                part_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError:
            continue

        os.close(descriptor)

        return part_path, target_path


def _write_backup(
    connection: sqlite3.Connection,
    part_path: Path,
) -> None:
    target = sqlite3.connect(str(part_path))

    try:
        connection.backup(target)
    finally:
        target.close()


def _validate_backup(part_path: Path, db_path: str) -> None:
    target = sqlite3.connect(str(part_path))

    try:
        row = target.execute("PRAGMA quick_check").fetchone()
    finally:
        target.close()

    if row is None or row[0] != "ok":
        detail = "" if row is None else str(row[0])

        raise DatabaseBackupError(
            f"Refusing to keep backup of {db_path}: "
            f"quick_check reported {detail!r}."
        )


def _discard_backup(part_path: Path | None) -> None:
    if part_path is None:
        return

    try:
        part_path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning(
            "could not remove incomplete backup %s: %s",
            part_path,
            exc,
        )


def prune_old_backup_files(
    db_path: str,
    retention: int = BACKUP_RETENTION,
) -> list[Path]:
    backups_dir = backups_directory(db_path)
    pattern = f"{Path(db_path).stem}-*.db"

    backups = sorted(
        backups_dir.glob(pattern),
        key=lambda path: path.name,
        reverse=True,
    )

    removed = []

    for path in backups[max(retention, 0):]:
        path.unlink(missing_ok=True)
        removed.append(path)

    return removed


def _assert_database_is_healthy(
    connection: sqlite3.Connection,
    db_path: str,
) -> None:
    row = connection.execute("PRAGMA quick_check").fetchone()

    if row is None or row[0] != "ok":
        detail = "" if row is None else str(row[0])

        raise DatabaseBackupError(
            f"Refusing to back up {db_path}: "
            f"quick_check reported {detail!r}."
        )


def _apply_migration(
    connection: sqlite3.Connection,
    migration: Migration,
) -> None:
    # BEGIN IMMEDIATE + in-transaction version check: a concurrent
    # process may have applied this migration after run_migrations
    # read user_version; without the recheck both processes would
    # run the same ALTER TABLE and one would fail with
    # "duplicate column name".
    connection.execute("BEGIN IMMEDIATE")

    try:
        current = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        if current >= migration.version:
            connection.execute("COMMIT")

            logger.info(
                "migration already applied: %04d_%s",
                migration.version,
                migration.name,
            )

            return

        for statement in migration.statements:
            connection.execute(statement)

        if migration.adopt_legacy:
            _adopt_legacy_publications(connection)

        connection.execute(
            f"PRAGMA user_version = {migration.version}"
        )
        connection.execute("COMMIT")
    except BaseException:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            # never let a failed rollback mask the original
            # migration error
            logger.warning(
                "rollback failed for migration %04d_%s",
                migration.version,
                migration.name,
            )

        raise

    logger.info(
        "migration applied: %04d_%s",
        migration.version,
        migration.name,
    )


def _adopt_legacy_publications(
    connection: sqlite3.Connection,
) -> None:
    columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(publications)"
        ).fetchall()
    }

    for column, statement in LEGACY_PUBLICATION_COLUMNS.items():
        if column not in columns:
            connection.execute(statement)
