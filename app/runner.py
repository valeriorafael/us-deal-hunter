import argparse
import logging
import sqlite3
from datetime import datetime, timedelta

from app.config import AmazonConfig, TelegramConfig
from app.models.price_history import PriceHistory
from app.publication.base import (
    CHANNEL_TELEGRAM,
    CHANNEL_WEBSITE,
    DEFAULT_PUBLICATION_COOLDOWN,
    is_failure_status,
)
from app.publication.service import PublicationService
from app.publication.website import WebsitePublisher
from app.services.amazon_discovery import AmazonDiscovery
from app.services.database import (
    DatabaseBackupError,
    UnsupportedSchemaVersionError,
)
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
from app.services.resilience import (
    AMAZON_MIN_INTERVAL_SECONDS,
    DEFAULT_RUN_DEADLINE_SECONDS,
    Deadline,
    RateLimiter,
)
from app.services.run_summary import (
    KeywordOutcome,
    RunSummary,
    sanitize_error,
    sanitize_text,
)

logger = logging.getLogger(__name__)


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

    try:
        if repository.count_older_than(cutoff) == 0:
            return

        removed = repository.prune_older_than(cutoff)
    except (DatabaseBackupError, sqlite3.Error) as exc:
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


def _reconcile_stale_attempts(
    publication_service: PublicationService,
) -> int:
    """Resolve stale attempt rows once per run (phase 3).

    Reconciliation is housekeeping: if it fails the run still
    continues (the rows are picked up again on the next run).
    """
    try:
        return publication_service.reconcile_stale_attempts()
    except Exception as exc:
        logger.error(
            "stale reconciliation failed: %s",
            sanitize_error(exc),
        )
        return 0


def _verify_channel_attempts(
    publication_service: PublicationService,
) -> int:
    """Probe in-flight attempts against the channel (phase 4).

    Verification is housekeeping: if it fails the run still
    continues (the rows stay for the next attempt).
    """
    verify = getattr(
        publication_service,
        "verify_channel_attempts",
        None,
    )

    if verify is None:
        return 0

    try:
        return verify()
    except Exception as exc:
        logger.error(
            "channel verification failed: %s",
            sanitize_error(exc),
        )
        return 0


def run(
    args: argparse.Namespace,
    *,
    deadline: Deadline | None = None,
    rate_limiter: RateLimiter | None = None,
) -> int:
    if deadline is None:
        deadline = Deadline(DEFAULT_RUN_DEADLINE_SECONDS)

    if rate_limiter is None:
        rate_limiter = RateLimiter(
            AMAZON_MIN_INTERVAL_SECONDS
        )

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
            verifier=publisher,
            channel=CHANNEL_TELEGRAM,
        )

        # second channel: the website publisher shares the
        # same decision/cooldown pipeline, keyed by
        # CHANNEL_WEBSITE (spec 2.2/18.3). No verifier: the
        # static site carries no message handle to probe.
        website_service = PublicationService(
            publisher=WebsitePublisher(),
            deal_validator=CuratedDealValidator(),
            repository=PublicationRepository(),
            cooldown=DEDUPLICATION_COOLDOWN,
            channel=CHANNEL_WEBSITE,
        )

        verified = _verify_channel_attempts(
            publication_service
        )
        reconciled = _reconcile_stale_attempts(
            publication_service
        )

        publication_limit = (
            args.max_publications
            if args.max_publications is not None
            else config.max_publications_per_run
        )

        workflow = HuntWorkflow(
            discovery_workflow=None,
            publication_service=publication_service,
            policy=HuntPublicationPolicy(
                max_publications_per_run=publication_limit
            ),
        )

        result = workflow.publish_deals(
            deals,
            now=datetime.now(),
            deadline=deadline,
        )

        website_workflow = HuntWorkflow(
            discovery_workflow=None,
            publication_service=website_service,
            policy=HuntPublicationPolicy(
                max_publications_per_run=publication_limit
            ),
        )

        website_result = website_workflow.publish_deals(
            deals,
            now=datetime.now(),
            deadline=deadline,
        )

        summary_errors: list[str] = []

        for deal, publication_result in zip(
            deals,
            result.results,
        ):
            print(
                f"{deal.product.product_id}: "
                f"{publication_result.status} - "
                f"{sanitize_text(publication_result.reason)}"
            )

            if is_failure_status(
                publication_result.status
            ):
                summary_errors.append(
                    f"publication: "
                    f"{deal.product.product_id}: "
                    f"{sanitize_text(publication_result.reason)}"
                )

        summary = RunSummary(
            keyword_outcomes=[],
            deals_found=len(deals),
            publications_attempted=len(result.results),
            publications_successful=result.published_count,
            publications_failed=(
                len(result.results)
                - result.published_count
            ),
            duplicates_blocked=result.duplicate_count,
            reconciled=reconciled,
            deadline_exceeded=(
                deadline.expired
                or result.deadline_exceeded
            ),
            errors=summary_errors,
            publication_limit=publication_limit,
            channel_verified=verified,
        )

        print("")

        for line in summary.lines():
            print(line)

        print(
            f"Website published: "
            f"{website_result.published_count}/"
            f"{len(website_result.results)}."
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
    website_service = None

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
            verifier=publisher,
            channel=CHANNEL_TELEGRAM,
        )

        # same gate as telegram on purpose: the website
        # channel publishes whenever telegram publishes
        # (spec 2.2/18.3). No verifier: the static site
        # carries no message handle to probe.
        website_service = PublicationService(
            publisher=WebsitePublisher(),
            repository=repository,
            cooldown=DEDUPLICATION_COOLDOWN,
            channel=CHANNEL_WEBSITE,
        )

    all_deals = []
    outcomes: list[KeywordOutcome] = []
    errors: list[str] = []

    for keyword in keyword_configs:
        if deadline.expired:
            outcomes.append(
                KeywordOutcome(
                    keyword.query,
                    "SKIPPED",
                    0,
                    None,
                )
            )
            continue

        print("")
        print("========================================")
        print(f"Keyword: {keyword.query}")
        print("========================================")

        try:
            if not args.demo:
                rate_limiter.wait()

            deals = discovery_workflow.discover_deals(
                keywords=keyword.query,
                search_index=keyword.search_index,
                item_count=keyword.item_count,
                item_page=keyword.item_page,
                min_saving_percent=keyword.min_saving_percent,
                now=now,
            )
        except Exception as exc:
            # a failing keyword never aborts the run (phase 3)
            message = sanitize_error(exc)

            logger.error(
                "keyword failed: %s - %s",
                keyword.query,
                message,
            )
            outcomes.append(
                KeywordOutcome(
                    keyword.query,
                    "FAILED",
                    0,
                    message,
                )
            )
            errors.append(
                f"keyword: {keyword.query}: {message}"
            )
            continue

        outcomes.append(
            KeywordOutcome(
                keyword.query,
                "OK",
                len(deals),
                None,
            )
        )

        product_errors = getattr(
            discovery_workflow,
            "product_errors",
            None,
        )

        if product_errors:
            errors.extend(product_errors)
            product_errors.clear()

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
    attempted = 0
    duplicates_blocked = 0
    reconciled = 0
    verified = 0
    website_result = None
    deadline_flag = deadline.expired

    if publication_service is not None:
        verified = _verify_channel_attempts(
            publication_service
        )
        reconciled = _reconcile_stale_attempts(
            publication_service
        )

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
            deadline=deadline,
        )

        published = result.published_count
        attempted = len(result.results)
        duplicates_blocked = result.duplicate_count
        deadline_flag = (
            deadline.expired or result.deadline_exceeded
        )

        for deal, publication_result in zip(
            all_deals,
            result.results,
        ):
            try:
                print(
                    f"{deal.product.product_id}: "
                    f"{publication_result.status} - "
                    f"{sanitize_text(publication_result.reason)}"
                )
            except Exception as exc:
                # last line of defence per deal (phase 3)
                errors.append(
                    f"publication: "
                    f"{deal.product.product_id}: "
                    f"{sanitize_error(exc)}"
                )
                continue

            if is_failure_status(
                publication_result.status
            ):
                errors.append(
                    f"publication: "
                    f"{deal.product.product_id}: "
                    f"{sanitize_text(publication_result.reason)}"
                )

        if website_service is not None:
            # second channel: same deals, same deadline and
            # same per-run limit (spec 2.2/18.3)
            website_hunt = HuntWorkflow(
                discovery_workflow=discovery_workflow,
                publication_service=website_service,
                policy=HuntPublicationPolicy(
                    max_publications_per_run=max_publications
                ),
            )

            website_result = website_hunt.publish_deals(
                all_deals,
                now=now,
                deadline=deadline,
            )

    summary = RunSummary(
        keyword_outcomes=outcomes,
        deals_found=total_deals,
        publications_attempted=attempted,
        publications_successful=published,
        publications_failed=attempted - published,
        duplicates_blocked=duplicates_blocked,
        reconciled=reconciled,
        deadline_exceeded=deadline_flag,
        errors=errors,
        publication_limit=max_publications,
        channel_verified=verified,
    )

    print("")

    for line in summary.lines():
        print(line)

    if website_result is not None:
        print(
            f"Website published: "
            f"{website_result.published_count}/"
            f"{len(website_result.results)}."
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
    except (
        sqlite3.Error,
        UnsupportedSchemaVersionError,
    ) as exc:
        # corrupt schema, disk full, locked database: clean
        # one-line error instead of a raw traceback
        print(f"Database error: {exc}")
        return 4


if __name__ == "__main__":
    raise SystemExit(main())

