from app.runner import create_parser, format_deal


def test_runner_parser_requires_keywords():
    parser = create_parser()

    try:
        parser.parse_args([])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError(
            "Keywords should be required."
        )


def test_runner_parser_accepts_dry_run():
    parser = create_parser()

    args = parser.parse_args(
        [
            "--keywords",
            "gaming mouse",
            "--search-index",
            "Electronics",
            "--item-count",
            "5",
            "--min-saving-percent",
            "20",
            "--dry-run",
        ]
    )

    assert args.keywords == "gaming mouse"
    assert args.search_index == "Electronics"
    assert args.item_count == 5
    assert args.min_saving_percent == 20
    assert args.dry_run is True


def test_format_deal_contains_core_information():
    from app.models.deal import Deal
    from app.models.product import Product

    deal = Deal(
        product=Product(
            product_id="123",
            title="Gaming Mouse",
            current_price=75.0,
            average_price_30d=100.0,
            platform="amazon",
            affiliate_url="https://example.com",
        ),
        score=82.0,
        confidence="HIGH",
    )

    output = format_deal(deal)

    assert "[82]" in output
    assert "Gaming Mouse" in output
    assert "$75.00" in output
    assert "Confidence: HIGH" in output
    assert "Affiliate: YES" in output

def test_runner_parser_accepts_demo():
    parser = create_parser()

    args = parser.parse_args(
        [
            "--keywords",
            "gaming mouse",
            "--demo",
        ]
    )

    assert args.keywords == "gaming mouse"
    assert args.demo is True


def test_runner_demo_mode_is_safe():
    parser = create_parser()

    args = parser.parse_args(
        [
            "--keywords",
            "gaming mouse",
            "--demo",
        ]
    )

    assert args.demo is True

def test_runner_parser_accepts_publish_demo():
    parser = create_parser()

    args = parser.parse_args(
        [
            "--keywords",
            "gaming mouse",
            "--demo",
            "--publish-demo",
        ]
    )

    assert args.demo is True
    assert args.publish_demo is True


def test_publish_demo_requires_demo(monkeypatch):
    from argparse import Namespace
    from app.runner import run

    args = Namespace(
        keywords="gaming mouse",
        search_index="All",
        item_count=10,
        item_page=1,
        min_saving_percent=None,
        dry_run=False,
        demo=False,
        publish_demo=True,
    )

    try:
        run(args)
    except ValueError as exc:
        assert "--publish-demo requires --demo" in str(exc)
    else:
        raise AssertionError(
            "publish-demo should require demo mode."
        )

def test_runner_parser_accepts_publish_demo():
    parser = create_parser()

    args = parser.parse_args(
        [
            "--keywords",
            "gaming mouse",
            "--demo",
            "--publish-demo",
        ]
    )

    assert args.demo is True
    assert args.publish_demo is True


def test_publish_demo_requires_demo(monkeypatch):
    from argparse import Namespace
    from app.runner import run

    args = Namespace(
        keywords="gaming mouse",
        search_index="All",
        item_count=10,
        item_page=1,
        min_saving_percent=None,
        dry_run=False,
        demo=False,
        publish_demo=True,
    )

    try:
        run(args)
    except ValueError as exc:
        assert "--publish-demo requires --demo" in str(exc)
    else:
        raise AssertionError(
            "publish-demo should require demo mode."
        )

def test_runner_parser_accepts_keywords_file():
    parser = create_parser()

    args = parser.parse_args(
        [
            "--keywords-file",
            "data/keywords.json",
            "--dry-run",
        ]
    )

    assert args.keywords_file == (
        "data/keywords.json"
    )
    assert args.dry_run is True


def test_runner_parser_rejects_both_keyword_sources():
    parser = create_parser()

    try:
        parser.parse_args(
            [
                "--keywords",
                "gaming mouse",
                "--keywords-file",
                "data/keywords.json",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError(
            "Both keyword sources should not be accepted."
        )

def test_runner_parser_accepts_publication_limit():
    parser = create_parser()

    args = parser.parse_args(
        [
            "--keywords",
            "gaming mouse",
            "--max-publications",
            "5",
        ]
    )

    assert args.max_publications == 5


def test_prune_old_history_keeps_ninety_day_window(tmp_path):
    from datetime import datetime, timedelta

    from app.models.price_history import PriceHistory
    from app.runner import _prune_old_history
    from app.services.price_history_repository import (
        PriceHistoryRepository,
    )

    now = datetime(2026, 8, 15)

    repository = PriceHistoryRepository(
        str(tmp_path / "prune.db")
    )

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

    _prune_old_history(repository, now)

    remaining = repository.get_by_product("123")

    assert len(remaining) == 3
    assert [
        item.recorded_at for item in remaining
    ] == [
        now - timedelta(days=90),
        now - timedelta(days=45),
        now,
    ]


def test_runner_wires_deduplication_cooldown(monkeypatch):
    from argparse import Namespace
    from datetime import timedelta
    from types import SimpleNamespace

    import app.runner as runner_module
    import app.services.curated_deals as curated_deals
    from app.publication.base import DEFAULT_PUBLICATION_COOLDOWN

    recorded = []

    def record_publication_service(**kwargs):
        recorded.append(kwargs)
        return object()

    class FakeTelegramConfig:
        @classmethod
        def from_environment(cls):
            return cls()

        def create_publisher(self):
            return object()

    class FakePublicationRepository:
        def __init__(self, *args, **kwargs):
            pass

    class FakeDiscoveryWorkflow:
        def discover_deals(self, **kwargs):
            return []

    class FakeCuratedDealLoader:
        def load(self, path=None):
            return SimpleNamespace(
                deals=[],
                max_publications_per_run=3,
            )

    monkeypatch.setattr(
        runner_module,
        "PublicationService",
        record_publication_service,
    )
    monkeypatch.setattr(
        runner_module,
        "TelegramConfig",
        FakeTelegramConfig,
    )
    monkeypatch.setattr(
        runner_module,
        "PublicationRepository",
        FakePublicationRepository,
    )
    monkeypatch.setattr(
        runner_module,
        "build_discovery_workflow",
        lambda **kwargs: FakeDiscoveryWorkflow(),
    )
    monkeypatch.setattr(
        curated_deals,
        "CuratedDealLoader",
        FakeCuratedDealLoader,
    )

    demo_result = runner_module.run(
        Namespace(
            keywords="gaming mouse",
            search_index="All",
            item_count=10,
            item_page=1,
            min_saving_percent=None,
            max_publications=None,
            keywords_file=None,
            curated_file=None,
            dry_run=False,
            demo=True,
            publish_demo=True,
        )
    )

    curated_result = runner_module.run(
        Namespace(
            keywords=None,
            keywords_file=None,
            curated_file="data/curated_deals.json",
            demo=False,
            publish_demo=False,
            dry_run=False,
            max_publications=None,
        )
    )

    assert demo_result == 0
    assert curated_result == 0
    assert len(recorded) == 2

    for call in recorded:
        assert (
            call["cooldown"]
            == runner_module.DEDUPLICATION_COOLDOWN
            == DEFAULT_PUBLICATION_COOLDOWN
            == timedelta(hours=24)
        )


def test_prune_old_history_aborts_when_backup_fails(
    tmp_path,
    monkeypatch,
    capsys,
):
    from datetime import datetime, timedelta

    from app.models.price_history import PriceHistory
    from app.runner import _prune_old_history
    from app.services import price_history_repository
    from app.services.database import DatabaseBackupError
    from app.services.price_history_repository import (
        PriceHistoryRepository,
    )

    now = datetime(2026, 8, 15)

    repository = PriceHistoryRepository(
        str(tmp_path / "backup_failure.db")
    )

    repository.save(
        PriceHistory(
            "123",
            100.0,
            recorded_at=now - timedelta(days=200),
        )
    )

    def fail_backup(connection, db_path):
        raise DatabaseBackupError("disk full")

    monkeypatch.setattr(
        price_history_repository,
        "backup_database",
        fail_backup,
    )

    _prune_old_history(repository, now)

    captured = capsys.readouterr()

    assert "History prune aborted" in captured.out
    assert "disk full" in captured.out
    assert len(repository.get_by_product("123")) == 1


def test_prune_old_history_skips_backup_without_old_rows(
    tmp_path,
    monkeypatch,
    capsys,
):
    from datetime import datetime, timedelta

    from app.models.price_history import PriceHistory
    from app.runner import _prune_old_history
    from app.services import price_history_repository
    from app.services.database import DatabaseBackupError
    from app.services.price_history_repository import (
        PriceHistoryRepository,
    )

    now = datetime(2026, 8, 15)

    repository = PriceHistoryRepository(
        str(tmp_path / "recent_only.db")
    )

    repository.save(
        PriceHistory(
            "123",
            100.0,
            recorded_at=now - timedelta(days=10),
        )
    )

    def fail_backup(connection, db_path):
        raise DatabaseBackupError("should not run")

    monkeypatch.setattr(
        price_history_repository,
        "backup_database",
        fail_backup,
    )

    _prune_old_history(repository, now)

    captured = capsys.readouterr()

    assert captured.out == ""
    assert len(repository.get_by_product("123")) == 1


def test_main_reports_backup_errors_without_traceback(
    monkeypatch,
    capsys,
):
    import app.runner as runner_module
    from app.services.database import DatabaseBackupError

    def failing_run(args):
        raise DatabaseBackupError("disk full")

    monkeypatch.setattr(runner_module, "run", failing_run)
    monkeypatch.setattr(
        "sys.argv",
        ["run.py", "--keywords", "gaming mouse"],
    )

    code = runner_module.main()

    captured = capsys.readouterr()

    assert code == 3
    assert "Database backup error" in captured.out
    assert "disk full" in captured.out
    assert "Traceback" not in captured.out
