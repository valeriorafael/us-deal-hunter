import argparse
from datetime import datetime, timedelta

from app.config import AmazonConfig, TelegramConfig
from app.models.price_history import PriceHistory
from app.publication.base import DEFAULT_PUBLICATION_COOLDOWN
from app.publication.service import PublicationService
from app.services.amazon_discovery import AmazonDiscovery
from app.services.database import DatabaseBackupError
from app.services.deal_pipeline import DealPipeline
from app.services.demo_discovery import DemoAmazonDiscovery
from app.services.discovery_workflow import DiscoveryWorkflow
from app.services.hunt_policy import HuntPublicationPolicy
from app.services.hunt_workflow import HuntWorkflow
from app.services.keyword_config import (
    KeywordConfig,
    KeywordConfigLoader,
)
from app.services.price_history_repository import PriceHistoryRepository
from app.services.publication_repository import (
    PublicationRepository,
)


DEMO_DB_PATH = ":memory:"
DEMO_PUBLICATION_DB_PATH = "data/demo_publication.db"

HISTORY_RETENTION_DAYS = 90

# Deduplication policy for the hunter: a product is published
# again only after this window has fully elapsed. The value is
# owned by app.publication.base.DEFAULT_PUBLICATION_COOLDOWN so
# there is a single place to change it. Assign None here to
# disable re-publication entirely.
DEDUPLICATION_COOLDOWN = DEFAULT_PUBLICATION_COOLDOWN


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="US Deal Hunter runner."
    )

    keyword_group = parser.add_mutually_exclusive_group(
        required=True
    )
    keyword_group.add_argument(
        "--curated-file",
        help="JSON file containing verified current Amazon deals.",
    )

    keyword_group.add_argument(
        "--keywords",
        help="Single Amazon search query.",
    )

    keyword_group.add_argument(
        "--keywords-file",
        help="JSON file containing multiple search queries.",
    )

    parser.add_argument(
        "--search-index",
        default="All",
        help="Amazon search category.",
    )

    parser.add_argument(
        "--item-count",
        type=int,
        default=10,
        help="Number of products to request.",
    )

    parser.add_argument(
        "--item-page",
        type=int,
        default=1,
        help="Search result page.",
    )

    parser.add_argument(
        "--min-saving-percent",
        type=float,
        default=None,
        help="Minimum Amazon saving percentage.",
    )

    parser.add_argument(
        "--max-publications",
        type=int,
        default=None,
        help="Maximum successful publications for one run.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate deals without publishing.",
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run using local demo data without Amazon.",
    )

    parser.add_argument(
        "--publish-demo",
        action="store_true",
        help="Publish demo deals to Telegram. Requires --demo.",
    )

    return parser


def _seed_demo_history(
    repository: PriceHistoryRepository,
    now: datetime,
) -> None:
    products = [
        (
            "B08N5WRWNW",
            [
                (60, 110.0),
                (45, 105.0),
                (30, 100.0),
                (20, 95.0),
                (10, 100.0),
            ],
        ),
    ]

    for product_id, history in products:
        if repository.count(product_id) > 0:
            continue

        for days_ago, price in history:
            repository.save(
                PriceHistory(
                    product_id=product_id,
                    price=price,
                    currency="USD",
                    recorded_at=now - timedelta(
                        days=days_ago
                    ),
                )
            )


def _prune_old_history(
    repository: PriceHistoryRepository,
    now: datetime,
) -> None:
    cutoff = now - timedelta(
        days=HISTORY_RETENTION_DAYS
    )

    if repository.count_older_than(cutoff) == 0:
        return

    try:
        removed = repository.prune_older_than(cutoff)
    except DatabaseBackupError as exc:
        print(f"History prune aborted: {exc}")

        return

    if removed:
        print(
            f"History pruned: {removed} entries "
            f"older than {HISTORY_RETENTION_DAYS} days."
        )


def build_discovery_workflow(
    demo: bool = False,
    now: datetime | None = None,
) -> DiscoveryWorkflow:
    now = now or datetime.now()

    if demo:
        repository = PriceHistoryRepository(
            DEMO_DB_PATH
        )

        _seed_demo_history(
            repository,
            now,
        )

        discovery = DemoAmazonDiscovery()

        return DiscoveryWorkflow(
            discovery=discovery,
            pipeline=DealPipeline(
                repository=repository,
            ),
        )

    amazon_config = AmazonConfig.from_environment()
    client = amazon_config.create_client()

    repository = PriceHistoryRepository()

    _prune_old_history(
        repository,
        now,
    )

    discovery = AmazonDiscovery(
        client=client,
    )

    return DiscoveryWorkflow(
        discovery=discovery,
        pipeline=DealPipeline(
            repository=repository,
        ),
    )


def build_keyword_configs(
    args: argparse.Namespace,
) -> tuple[list[KeywordConfig], int]:
    if args.keywords:
        return [
            KeywordConfig(
                query=args.keywords,
                search_index=args.search_index,
                item_count=args.item_count,
                item_page=args.item_page,
                min_saving_percent=args.min_saving_percent,
            )
        ], (
            args.max_publications
            if args.max_publications is not None
            else 3
        )

    config = KeywordConfigLoader.load_config(
        args.keywords_file
    )

    return list(config.keywords), (
        args.max_publications
        if args.max_publications is not None
        else config.max_publications_per_run
    )


def format_deal(deal) -> str:
    product = deal.product

    lines = [
        f"[{deal.score:.0f}] {product.title}",
        f"Price: ${product.current_price:.2f}",
        f"Confidence: {deal.confidence}",
    ]

    if product.discount_vs_30d is not None:
        lines.append(
            f"30d discount: {product.discount_vs_30d:.1%}"
        )

    lines.append(
        f"Affiliate: {'YES' if product.affiliate_url else 'NO'}"
    )

    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    if args.publish_demo and not args.demo:
        raise ValueError(
            "--publish-demo requires --demo."
        )

    if args.curated_file:
        if (
            args.keywords
            or args.keywords_file
            or args.demo
        ):
            raise ValueError(
                "--curated-file must be used by itself."
            )

        from app.deals.curated_validator import (
            CuratedDealValidator,
        )
        from app.services.curated_deals import (
            CuratedDealLoader,
        )

        config = CuratedDealLoader().load(
    args.curated_file
)

        deals = list(config.deals)

        print("")
        print("=== US DEAL HUNTER - CURATED LIVE ===")
        print(
            f"Verified deals loaded: {len(deals)}"
        )
        print("")

        for index, deal in enumerate(
            deals,
            start=1,
        ):
            print(
                f"--- Deal {index} ---"
            )
            print(
                format_deal(deal)
            )
            print("")

        if args.dry_run:
            print(
                "DRY RUN: nothing was published."
            )
            return 0

        telegram_config = (
            TelegramConfig.from_environment()
        )

        publisher = (
            telegram_config.create_publisher()
        )

        publication_service = PublicationService(
            publisher=publisher,
            deal_validator=CuratedDealValidator(),
            repository=PublicationRepository(),
            cooldown=DEDUPLICATION_COOLDOWN,
        )

        workflow = HuntWorkflow(
            discovery_workflow=None,
            publication_service=publication_service,
            policy=HuntPublicationPolicy(
                max_publications_per_run=(
                    args.max_publications
                    if args.max_publications is not None
                    else config.max_publications_per_run
                )
            ),
        )

        result = workflow.publish_deals(
            deals,
            now=datetime.now(),
        )

        for deal, publication_result in zip(
            deals,
            result.results,
        ):
            print(
                f"{deal.product.product_id}: "
                f"{publication_result.status} - "
                f"{publication_result.reason}"
            )

        print("")
        print(
            f"Publication complete: "
            f"{result.published_count}/"
            f"{result.discovered_count} published."
        )

        return 0

    # resto da fun��o atual:
        raise ValueError(
            "--curated-file must be used by itself."
        )
    if args.publish_demo and not args.demo:
        raise ValueError(
            "--publish-demo requires --demo."
        )

    if (
        args.max_publications is not None
        and args.max_publications < 1
    ):
        raise ValueError(
            "--max-publications must be at least 1."
        )

    now = datetime.now()

    keyword_configs, max_publications = build_keyword_configs(
        args
    )

    if args.demo:
        print("")
        print("=== US DEAL HUNTER - DEMO MODE ===")
        print("No Amazon API request will be made.")

        if args.publish_demo:
            print("Telegram publication is ENABLED.")
        else:
            print("No Telegram message will be sent.")

        print("")

    discovery_workflow = build_discovery_workflow(
        demo=args.demo,
        now=now,
    )

    publication_service = None

    if not args.dry_run and (
        not args.demo or args.publish_demo
    ):
        telegram_config = TelegramConfig.from_environment()

        publisher = telegram_config.create_publisher()

        repository = (
            PublicationRepository(
                DEMO_PUBLICATION_DB_PATH
            )
            if args.demo
            else PublicationRepository()
        )

        publication_service = PublicationService(
            publisher=publisher,
            repository=repository,
            cooldown=DEDUPLICATION_COOLDOWN,
        )

    all_deals = []

    for keyword in keyword_configs:
        print("")
        print("========================================")
        print(f"Keyword: {keyword.query}")
        print("========================================")

        deals = discovery_workflow.discover_deals(
            keywords=keyword.query,
            search_index=keyword.search_index,
            item_count=keyword.item_count,
            item_page=keyword.item_page,
            min_saving_percent=keyword.min_saving_percent,
            now=now,
        )

        all_deals.extend(deals)

        print(f"Deals found: {len(deals)}")
        print("")

        for index, deal in enumerate(
            deals,
            start=1,
        ):
            print(f"--- Deal {index} ---")
            print(format_deal(deal))
            print("")

    all_deals.sort(
        key=lambda deal: deal.score,
        reverse=True,
    )

    total_deals = len(all_deals)
    published = 0

    if publication_service is not None:
        hunt = HuntWorkflow(
            discovery_workflow=discovery_workflow,
            publication_service=publication_service,
            policy=HuntPublicationPolicy(
                max_publications_per_run=max_publications
            ),
        )

        result = hunt.publish_deals(
            all_deals,
            now=now,
        )

        published = result.published_count

        for deal, publication_result in zip(
            all_deals,
            result.results,
        ):
            print(
                f"{deal.product.product_id}: "
                f"{publication_result.status} - "
                f"{publication_result.reason}"
            )

    print("")
    print("========================================")
    print("SUMMARY")
    print("========================================")
    print(
        f"Keywords processed: "
        f"{len(keyword_configs)}"
    )
    print(f"Deals found: {total_deals}")
    print(
        f"Publication limit: "
        f"{max_publications}"
    )

    if args.dry_run or (
        args.demo and not args.publish_demo
    ):
        print("DRY RUN: nothing was published.")
    else:
        print(
            f"Publication complete: "
            f"{published}/{total_deals} published."
        )

    return 0


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()

    try:
        return run(args)
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 2
    except DatabaseBackupError as exc:
        print(f"Database backup error: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

