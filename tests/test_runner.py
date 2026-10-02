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


def build_runner_deal(product_id):
    from app.models.deal import Deal
    from app.models.product import Product

    return Deal(
        product=Product(
            product_id=product_id,
            title=f"Product {product_id}",
            current_price=75.0,
            average_price_30d=100.0,
            lowest_price_90d=70.0,
            rating=4.7,
            review_count=8500,
            platform="amazon",
            affiliate_url=(
                f"https://www.amazon.com/dp/{product_id}"
                "?tag=test-20"
            ),
        ),
        score=88.0,
        label="GREAT",
        confidence="HIGH",
    )


def build_runner_namespace(**overrides):
    from argparse import Namespace

    values = {
        "keywords": "gaming mouse",
        "search_index": "All",
        "item_count": 10,
        "item_page": 1,
        "min_saving_percent": None,
        "max_publications": None,
        "keywords_file": None,
        "curated_file": None,
        "dry_run": True,
        "demo": True,
        "publish_demo": False,
    }
    values.update(overrides)

    return Namespace(**values)


def build_keyword_configs_stub(queries, limit=3):
    import app.runner as runner_module

    configs = [
        runner_module.KeywordConfig(
            query=query,
            search_index="All",
            item_count=10,
            item_page=1,
            min_saving_percent=None,
        )
        for query in queries
    ]

    return lambda args: (configs, limit)


def test_runner_isolates_keyword_failures(
    monkeypatch,
    capsys,
):
    import app.runner as runner_module

    calls = []

    class ScriptedDiscovery:
        def __init__(self):
            self.product_errors = []

        def discover_deals(self, *, keywords, **kwargs):
            calls.append(keywords)

            if keywords == "bad mouse":
                raise TimeoutError(
                    "search timed out token=secret123"
                )

            return [build_runner_deal(f"B00{len(calls)}")]

    monkeypatch.setattr(
        runner_module,
        "build_discovery_workflow",
        lambda **kwargs: ScriptedDiscovery(),
    )
    monkeypatch.setattr(
        runner_module,
        "build_keyword_configs",
        build_keyword_configs_stub(
            ["good one", "bad mouse", "good two"]
        ),
    )

    code = runner_module.run(build_runner_namespace())

    captured = capsys.readouterr().out

    assert code == 0
    assert calls == ["good one", "bad mouse", "good two"]
    assert "Keywords processed: 3" in captured
    assert "Keywords failed: 1" in captured
    assert "Keywords skipped: 0" in captured
    assert (
        "keyword: bad mouse: TimeoutError:"
        in captured
    )
    assert "token=[REDACTED]" in captured
    assert "secret123" not in captured
    assert captured.count("Deals found: 1") == 2


def test_runner_skips_keywords_when_deadline_expired(
    monkeypatch,
    capsys,
):
    import app.runner as runner_module

    from app.services.resilience import Deadline

    calls = []

    class ScriptedDiscovery:
        def __init__(self):
            self.product_errors = []

        def discover_deals(self, *, keywords, **kwargs):
            calls.append(keywords)
            return []

    monkeypatch.setattr(
        runner_module,
        "build_discovery_workflow",
        lambda **kwargs: ScriptedDiscovery(),
    )
    monkeypatch.setattr(
        runner_module,
        "build_keyword_configs",
        build_keyword_configs_stub(["one", "two"]),
    )

    deadline = Deadline(seconds=0, clock=lambda: 0.0)

    code = runner_module.run(
        build_runner_namespace(),
        deadline=deadline,
    )

    captured = capsys.readouterr().out

    assert code == 0
    assert calls == []
    assert "Keywords processed: 2" in captured
    assert "Keywords skipped: 2" in captured
    assert "Deadline exceeded: yes" in captured


def test_runner_waits_on_rate_limiter_per_keyword(
    monkeypatch,
    capsys,
):
    import app.runner as runner_module

    class SpyLimiter:
        def __init__(self):
            self.waits = 0

        def wait(self):
            self.waits += 1

    class EmptyDiscovery:
        def __init__(self):
            self.product_errors = []

        def discover_deals(self, **kwargs):
            return []

    monkeypatch.setattr(
        runner_module,
        "build_discovery_workflow",
        lambda **kwargs: EmptyDiscovery(),
    )
    monkeypatch.setattr(
        runner_module,
        "build_keyword_configs",
        build_keyword_configs_stub(["one", "two"]),
    )

    limiter = SpyLimiter()

    code = runner_module.run(
        build_runner_namespace(demo=False),
        rate_limiter=limiter,
    )

    assert code == 0
    assert limiter.waits == 2


def test_runner_demo_mode_skips_rate_limiter(
    monkeypatch,
    capsys,
):
    import app.runner as runner_module

    class SpyLimiter:
        def __init__(self):
            self.waits = 0

        def wait(self):
            self.waits += 1

    class EmptyDiscovery:
        def __init__(self):
            self.product_errors = []

        def discover_deals(self, **kwargs):
            return []

    monkeypatch.setattr(
        runner_module,
        "build_discovery_workflow",
        lambda **kwargs: EmptyDiscovery(),
    )
    monkeypatch.setattr(
        runner_module,
        "build_keyword_configs",
        build_keyword_configs_stub(["one"]),
    )

    limiter = SpyLimiter()

    code = runner_module.run(
        build_runner_namespace(demo=True),
        rate_limiter=limiter,
    )

    assert code == 0
    assert limiter.waits == 0


def test_runner_reconciles_stale_attempts_before_summary(
    tmp_path,
    monkeypatch,
    capsys,
):
    from datetime import datetime, timedelta

    import app.runner as runner_module
    from app.services.publication_repository import (
        PublicationRepository,
    )

    seeded = PublicationRepository(
        str(tmp_path / "reconcile.db")
    )
    attempt_id = seeded.begin_attempt(
        product_id="B0STALE",
        affiliate_url=(
            "https://www.amazon.com/dp/B0STALE?tag=test-20"
        ),
        price=75.0,
        attempted_at=datetime.now()
        - timedelta(seconds=601),
    )
    seeded.mark_sending(attempt_id)

    class FakeTelegramConfig:
        @classmethod
        def from_environment(cls):
            return cls()

        def create_publisher(self):
            return object()

    class EmptyDiscovery:
        def __init__(self):
            self.product_errors = []

        def discover_deals(self, **kwargs):
            return []

    monkeypatch.setattr(
        runner_module,
        "build_discovery_workflow",
        lambda **kwargs: EmptyDiscovery(),
    )
    monkeypatch.setattr(
        runner_module,
        "build_keyword_configs",
        build_keyword_configs_stub(["one"]),
    )
    monkeypatch.setattr(
        runner_module,
        "TelegramConfig",
        FakeTelegramConfig,
    )
    monkeypatch.setattr(
        runner_module,
        "PublicationRepository",
        lambda *args, **kwargs: seeded,
    )

    code = runner_module.run(
        build_runner_namespace(
            dry_run=False,
            demo=True,
            publish_demo=True,
        )
    )

    captured = capsys.readouterr().out
    row = seeded._connection.execute(
        "SELECT status FROM publications WHERE id = ?",
        (attempt_id,),
    ).fetchone()

    assert code == 0
    assert row[0] == "RECONCILIATION"
    assert "Reconciled unknown: 1" in captured
    assert "Deadline exceeded: no" in captured


def test_runner_publishes_deal_and_reports_summary(
    tmp_path,
    monkeypatch,
    capsys,
):
    import app.runner as runner_module
    from app.publication.base import PublicationResult
    from app.services.publication_repository import (
        PublicationRepository,
    )

    class FakePublisher:
        def publish(self, deal):
            return PublicationResult(
                success=True,
                status="PUBLISHED",
                reason="Published.",
                message_id=99,
            )

    class FakeTelegramConfig:
        @classmethod
        def from_environment(cls):
            return cls()

        def create_publisher(self):
            return FakePublisher()

    class DealDiscovery:
        def __init__(self):
            self.product_errors = []

        def discover_deals(self, **kwargs):
            return [build_runner_deal("B08PUB1")]

    repository = PublicationRepository(
        str(tmp_path / "summary.db")
    )

    monkeypatch.setattr(
        runner_module,
        "build_discovery_workflow",
        lambda **kwargs: DealDiscovery(),
    )
    monkeypatch.setattr(
        runner_module,
        "build_keyword_configs",
        build_keyword_configs_stub(["mouse"]),
    )
    monkeypatch.setattr(
        runner_module,
        "TelegramConfig",
        FakeTelegramConfig,
    )
    monkeypatch.setattr(
        runner_module,
        "PublicationRepository",
        lambda *args, **kwargs: repository,
    )

    code = runner_module.run(
        build_runner_namespace(
            dry_run=False,
            demo=True,
            publish_demo=True,
        )
    )

    captured = capsys.readouterr().out
    row = repository._connection.execute(
        "SELECT status, message_id FROM publications",
    ).fetchone()

    assert code == 0
    assert row == ("PUBLISHED", 99)
    assert "B08PUB1: PUBLISHED - Published." in captured
    assert "Keywords processed: 1" in captured
    assert "Keywords failed: 0" in captured
    assert "Deals found: 1" in captured
    assert "Publication limit: 3" in captured
    assert "Publications attempted: 1" in captured
    assert "Publications successful: 1" in captured
    assert "Publications failed: 0" in captured
    assert "Duplicates blocked: 0" in captured
    assert "Reconciled unknown: 0" in captured
    assert "Deadline exceeded: no" in captured
    assert "Errors (0):" in captured


def test_runner_surfaces_publication_exception_sanitized(
    tmp_path,
    monkeypatch,
    capsys,
):
    import app.runner as runner_module
    from app.services.publication_repository import (
        PublicationRepository,
    )

    class ExplodingPublisher:
        def publish(self, deal):
            raise RuntimeError("boom token=abc123")

    class FakeTelegramConfig:
        @classmethod
        def from_environment(cls):
            return cls()

        def create_publisher(self):
            return ExplodingPublisher()

    class DealDiscovery:
        def __init__(self):
            self.product_errors = []

        def discover_deals(self, **kwargs):
            return [build_runner_deal("B08ERR1")]

    repository = PublicationRepository(
        str(tmp_path / "error.db")
    )

    monkeypatch.setattr(
        runner_module,
        "build_discovery_workflow",
        lambda **kwargs: DealDiscovery(),
    )
    monkeypatch.setattr(
        runner_module,
        "build_keyword_configs",
        build_keyword_configs_stub(["mouse"]),
    )
    monkeypatch.setattr(
        runner_module,
        "TelegramConfig",
        FakeTelegramConfig,
    )
    monkeypatch.setattr(
        runner_module,
        "PublicationRepository",
        lambda *args, **kwargs: repository,
    )

    code = runner_module.run(
        build_runner_namespace(
            dry_run=False,
            demo=True,
            publish_demo=True,
        )
    )

    captured = capsys.readouterr().out
    row = repository._connection.execute(
        "SELECT status FROM publications",
    ).fetchone()

    assert code == 0
    assert row[0] == "RECONCILIATION"
    assert (
        "publication: B08ERR1: RuntimeError: boom"
        in captured
    )
    assert "token=[REDACTED]" in captured
    assert "abc123" not in captured
    assert "Errors (1):" in captured


def test_runner_adds_product_errors_to_summary(
    monkeypatch,
    capsys,
):
    import app.runner as runner_module

    class DiscoveryWithProductError:
        def __init__(self):
            self.product_errors = [
                "product: B00001 @ mouse: "
                "ValueError: bad price"
            ]

        def discover_deals(self, **kwargs):
            return []

    monkeypatch.setattr(
        runner_module,
        "build_discovery_workflow",
        lambda **kwargs: DiscoveryWithProductError(),
    )
    monkeypatch.setattr(
        runner_module,
        "build_keyword_configs",
        build_keyword_configs_stub(["mouse"]),
    )

    code = runner_module.run(build_runner_namespace())

    captured = capsys.readouterr().out

    assert code == 0
    assert "Errors (1):" in captured
    assert (
        "  - product: B00001 @ mouse: ValueError: bad price"
        in captured
    )


def test_runner_curated_reason_is_sanitized(
    monkeypatch,
    capsys,
):
    from argparse import Namespace
    from types import SimpleNamespace

    import app.runner as runner_module
    import app.services.curated_deals as curated_deals
    from app.publication.base import PublicationResult

    secret_token = "123456:AA-secret-token-value"

    class FakePublicationService:
        def __init__(self, **kwargs):
            pass

        def reconcile_stale_attempts(self):
            return 0

        def publish(self, deal, now=None):
            return PublicationResult(
                success=False,
                status="TELEGRAM_REQUEST_ERROR",
                reason=(
                    "HTTPSConnectionPool: Max retries exceeded "
                    f"with url: /bot{secret_token}/sendPhoto"
                ),
                indeterminate=True,
            )

    class FakeTelegramConfig:
        @classmethod
        def from_environment(cls):
            return cls()

        def create_publisher(self):
            return object()

    class FakePublicationRepository:
        def __init__(self, *args, **kwargs):
            pass

    class FakeCuratedDealLoader:
        def load(self, path=None):
            return SimpleNamespace(
                deals=[build_runner_deal("B0CUR1")],
                max_publications_per_run=3,
            )

    monkeypatch.setattr(
        runner_module,
        "PublicationService",
        FakePublicationService,
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
        curated_deals,
        "CuratedDealLoader",
        FakeCuratedDealLoader,
    )

    code = runner_module.run(
        Namespace(
            keywords=None,
            search_index="All",
            item_count=10,
            item_page=1,
            min_saving_percent=None,
            max_publications=None,
            keywords_file=None,
            curated_file="data/curated_deals.json",
            dry_run=False,
            demo=False,
            publish_demo=False,
        )
    )

    captured = capsys.readouterr()

    assert code == 0
    assert "TELEGRAM_REQUEST_ERROR" in captured.out
    assert secret_token not in captured.out
    assert "[REDACTED]" in captured.out


def test_runner_verifies_channel_before_summary(
    tmp_path,
    monkeypatch,
    capsys,
):
    from datetime import datetime, timedelta

    import app.runner as runner_module
    from app.publication.base import Verdict
    from app.services.publication_repository import (
        PublicationRepository,
    )

    seeded = PublicationRepository(
        str(tmp_path / "verify.db")
    )
    stale = datetime.now() - timedelta(seconds=601)
    attempt_id = seeded.begin_attempt(
        product_id="B0VER1",
        affiliate_url=(
            "https://www.amazon.com/dp/B0VER1?tag=test-20"
        ),
        price=75.0,
        attempted_at=stale,
    )
    seeded.mark_sending(attempt_id)
    seeded._connection.execute(
        "UPDATE publications SET message_id = 42 "
        "WHERE id = ?",
        (attempt_id,),
    )
    seeded._connection.commit()

    probe_calls = []

    class FakePublisher:
        def publish(self, deal):
            raise AssertionError("no deal to publish")

        def verify_message(self, message_id, *, affiliate_url):
            probe_calls.append(message_id)
            return Verdict.EXISTS

    class FakeTelegramConfig:
        @classmethod
        def from_environment(cls):
            return cls()

        def create_publisher(self):
            return FakePublisher()

    class EmptyDiscovery:
        def __init__(self):
            self.product_errors = []

        def discover_deals(self, **kwargs):
            return []

    monkeypatch.setattr(
        runner_module,
        "build_discovery_workflow",
        lambda **kwargs: EmptyDiscovery(),
    )
    monkeypatch.setattr(
        runner_module,
        "build_keyword_configs",
        build_keyword_configs_stub(["one"]),
    )
    monkeypatch.setattr(
        runner_module,
        "TelegramConfig",
        FakeTelegramConfig,
    )
    monkeypatch.setattr(
        runner_module,
        "PublicationRepository",
        lambda *args, **kwargs: seeded,
    )

    code = runner_module.run(
        build_runner_namespace(
            dry_run=False,
            demo=True,
            publish_demo=True,
        )
    )

    captured = capsys.readouterr().out
    row = seeded._connection.execute(
        "SELECT status, message_id FROM publications",
    ).fetchone()

    assert code == 0
    assert probe_calls == [42]
    assert row == ("PUBLISHED", 42)
    assert "Channel verified: 1" in captured
    assert "Reconciled unknown: 0" in captured


def test_runner_curated_emits_summary(
    monkeypatch,
    capsys,
):
    from argparse import Namespace
    from types import SimpleNamespace

    import app.runner as runner_module
    import app.services.curated_deals as curated_deals
    from app.publication.base import PublicationResult

    class FakePublicationService:
        def __init__(self, **kwargs):
            pass

        def reconcile_stale_attempts(self):
            return 0

        def publish(self, deal, now=None):
            return PublicationResult(
                success=True,
                status="PUBLISHED",
                reason="Published.",
                message_id=7,
            )

    class FakeTelegramConfig:
        @classmethod
        def from_environment(cls):
            return cls()

        def create_publisher(self):
            return object()

    class FakePublicationRepository:
        def __init__(self, *args, **kwargs):
            pass

    class FakeCuratedDealLoader:
        def load(self, path=None):
            return SimpleNamespace(
                deals=[build_runner_deal("B0CUR1")],
                max_publications_per_run=3,
            )

    monkeypatch.setattr(
        runner_module,
        "PublicationService",
        FakePublicationService,
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
        curated_deals,
        "CuratedDealLoader",
        FakeCuratedDealLoader,
    )

    code = runner_module.run(
        Namespace(
            keywords=None,
            search_index="All",
            item_count=10,
            item_page=1,
            min_saving_percent=None,
            max_publications=None,
            keywords_file=None,
            curated_file="data/curated_deals.json",
            dry_run=False,
            demo=False,
            publish_demo=False,
        )
    )

    captured = capsys.readouterr().out

    assert code == 0
    assert "SUMMARY" in captured
    assert "Keywords processed: 0" in captured
    assert "Keywords failed: 0" in captured
    assert "Deals found: 1" in captured
    assert "Publications successful: 1" in captured
    assert "Duplicates blocked: 0" in captured
    assert "Reconciled unknown: 0" in captured
    assert "Channel verified: 0" in captured
    assert "Deadline exceeded: no" in captured
    assert "Publication limit: 3" in captured
    assert "Publication complete: 1/1 published." in captured


def test_main_reports_sqlite_errors_without_traceback(
    monkeypatch,
    capsys,
):
    import sqlite3

    import app.runner as runner_module

    def failing_run(args):
        raise sqlite3.DatabaseError(
            "file is not a database"
        )

    monkeypatch.setattr(runner_module, "run", failing_run)
    monkeypatch.setattr(
        "sys.argv",
        ["run.py", "--keywords", "gaming mouse"],
    )

    code = runner_module.main()

    captured = capsys.readouterr()

    assert code == 4
    assert "Database error" in captured.out
    assert "file is not a database" in captured.out
    assert "Traceback" not in captured.out


def test_main_reports_unsupported_schema_without_traceback(
    monkeypatch,
    capsys,
):
    import app.runner as runner_module
    from app.services.database import (
        UnsupportedSchemaVersionError,
    )

    def failing_run(args):
        raise UnsupportedSchemaVersionError(
            "Database schema version 99 is newer than "
            "the supported version."
        )

    monkeypatch.setattr(runner_module, "run", failing_run)
    monkeypatch.setattr(
        "sys.argv",
        ["run.py", "--keywords", "gaming mouse"],
    )

    code = runner_module.main()

    captured = capsys.readouterr()

    assert code == 4
    assert "Database error" in captured.out
    assert "schema version 99" in captured.out
    assert "Traceback" not in captured.out


def test_prune_old_history_aborts_when_delete_fails(
    tmp_path,
    monkeypatch,
    capsys,
):
    from datetime import datetime, timedelta

    import sqlite3

    from app.models.price_history import PriceHistory
    from app.runner import _prune_old_history
    from app.services.price_history_repository import (
        PriceHistoryRepository,
    )

    now = datetime(2026, 8, 15)

    repository = PriceHistoryRepository(
        str(tmp_path / "locked.db")
    )

    repository.save(
        PriceHistory(
            "123",
            100.0,
            recorded_at=now - timedelta(days=200),
        )
    )

    def fail_delete(cutoff):
        raise sqlite3.OperationalError(
            "database is locked"
        )

    monkeypatch.setattr(
        repository,
        "delete_older_than",
        fail_delete,
    )

    _prune_old_history(repository, now)

    captured = capsys.readouterr()

    assert "History prune aborted" in captured.out
    assert "database is locked" in captured.out
    assert len(repository.get_by_product("123")) == 1
