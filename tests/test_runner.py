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
