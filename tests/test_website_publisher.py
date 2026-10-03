"""M4-B - website publisher contract (spec 18.1/18.3)."""

import ast
import inspect
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.models.deal import Deal
from app.models.product import Product
from app.publication.base import (
    CHANNEL_WEBSITE,
    STATUS_PUBLICATION_ERROR,
    STATUS_PUBLICATION_EXCEPTION,
    STATUS_PUBLISHED,
    STATUS_RECONCILIATION,
)
from app.publication.service import PublicationService
from app.publication.website import WebsitePublisher
from app.services.publication_repository import (
    PublicationRepository,
)

NOW = datetime(2026, 8, 15, 12, 0)

MODULE_PATH = Path("app/publication/website.py")

INVALID_REASON = "Invalid affiliate URL."

# sentinel: affiliate_url=None must stay expressible
DEFAULT_URL = object()


def build_deal(
    product_id="123",
    *,
    platform="amazon",
    affiliate_url=DEFAULT_URL,
):
    """Local builder: keeps this file independent of other tests."""
    if affiliate_url is DEFAULT_URL:
        affiliate_url = (
            f"https://www.amazon.com/dp/{product_id}?tag=test-20"
        )

    product = Product(
        product_id=product_id,
        title="Test Product",
        current_price=75.0,
        average_price_30d=100.0,
        lowest_price_90d=70.0,
        rating=4.7,
        review_count=8500,
        platform=platform,
        affiliate_url=affiliate_url,
    )

    return Deal(
        product=product,
        score=88.0,
        label="GREAT",
        confidence="HIGH",
    )


def rows_for(repository, product_id):
    return repository._connection.execute(
        "SELECT status, channel, message_id FROM publications "
        "WHERE product_id = ?",
        (product_id,),
    ).fetchall()


# ------------------------------------------------------------------
# A) WebsitePublisher
# ------------------------------------------------------------------


def test_publish_reports_published_for_affiliate_url():
    deal = build_deal()

    result = WebsitePublisher().publish(deal)

    assert result.success is True
    assert result.status == STATUS_PUBLISHED
    assert result.reason == "Deal published successfully."
    assert result.message_id is None
    assert result.indeterminate is False


@pytest.mark.parametrize(
    "url",
    [
        "http://www.amazon.com/dp/123?tag=test-20",
        "https://www.amazon.com/dp/123?tag=test-20",
        "https://example.com/offer",
        "https://example.com/offer?tag=secret-20",
    ],
)
def test_publish_accepts_http_urls(url):
    deal = build_deal(affiliate_url=url)

    result = WebsitePublisher().publish(deal)

    assert result.success is True
    assert result.status == STATUS_PUBLISHED
    assert result.message_id is None


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "notaurl",
        "www.amazon.com/dp/123",
        "/relative/path",
        "ftp://example.com/offer",
        " javascript:alert(1)",
    ],
)
def test_publish_rejects_non_http_urls(url):
    deal = build_deal(affiliate_url=url)

    result = WebsitePublisher().publish(deal)

    assert result.success is False
    assert result.status == STATUS_PUBLICATION_ERROR
    assert result.reason == INVALID_REASON
    assert result.message_id is None
    assert result.indeterminate is False


@pytest.mark.parametrize(
    "url",
    [None, 123, 12.5, b"https://example.com", ["https://example.com"]],
)
def test_publish_rejects_non_string_urls(url):
    deal = build_deal(affiliate_url=url)

    result = WebsitePublisher().publish(deal)

    assert result.success is False
    assert result.status == STATUS_PUBLICATION_ERROR
    assert result.reason == INVALID_REASON


@pytest.mark.parametrize(
    "url",
    [
        "notaurl",
        "www.amazon.com/dp/123?tag=super-secret-20",
        "javascript:alert('tag=super-secret-20')",
        "/dp/123?tag=super-secret-20",
    ],
)
def test_failure_reason_never_leaks_the_url(url):
    deal = build_deal(affiliate_url=url)

    result = WebsitePublisher().publish(deal)

    assert result.success is False
    assert result.reason == INVALID_REASON
    assert url not in result.reason
    assert "tag" not in result.reason
    assert "secret" not in result.reason


def test_success_reason_never_leaks_the_url():
    deal = build_deal(
        affiliate_url=(
            "https://www.amazon.com/dp/123?tag=super-secret-20"
        )
    )

    result = WebsitePublisher().publish(deal)

    assert result.reason == "Deal published successfully."
    assert "tag" not in result.reason
    assert "secret" not in result.reason


def test_publisher_needs_no_arguments():
    signature = inspect.signature(WebsitePublisher)

    assert (
        [
            parameter
            for parameter in signature.parameters.values()
            if parameter.default is inspect.Parameter.empty
            and parameter.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        ]
        == []
    )
    assert isinstance(WebsitePublisher(), WebsitePublisher)


def test_website_publisher_avoids_forbidden_dependencies():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))

    imported = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(
                alias.name for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)

    roots = {name.split(".")[0] for name in imported}

    # no network, no environment, no filesystem, no database
    assert roots.isdisjoint(
        {
            "requests",
            "dotenv",
            "flask",
            "telebot",
            "os",
            "pathlib",
            "sqlite3",
            "socket",
            "urllib",
            "http",
        }
    )

    # only project modules and logging may be imported
    assert roots.issubset({"app", "logging"})

    attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }
    names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }

    assert "environ" not in attributes
    assert "getenv" not in attributes
    assert "environ" not in names
    assert "getenv" not in names

    # the publisher never writes anything
    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name)
            and node.func.id == "open"
            or isinstance(node.func, ast.Attribute)
            and node.func.attr == "open"
        )
    ]


# ------------------------------------------------------------------
# B) PublicationService + WebsitePublisher
# ------------------------------------------------------------------


def test_service_records_website_publication(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "website_published.db")
    )
    deal = build_deal()

    result = PublicationService(
        publisher=WebsitePublisher(),
        repository=repository,
        channel=CHANNEL_WEBSITE,
    ).publish(deal, now=NOW)

    stored = rows_for(repository, deal.product.product_id)
    repository.close()

    assert result.success is True
    assert result.status == STATUS_PUBLISHED
    assert stored == [
        (STATUS_PUBLISHED, CHANNEL_WEBSITE, None)
    ]


def test_service_drops_attempt_when_url_is_invalid(tmp_path):
    repository = PublicationRepository(
        str(tmp_path / "website_invalid.db")
    )
    # non-Amazon platform: the deal passes DealValidator so the
    # website publisher is the one rejecting the URL
    deal = build_deal(
        platform="other", affiliate_url="notaurl"
    )

    result = PublicationService(
        publisher=WebsitePublisher(),
        repository=repository,
        channel=CHANNEL_WEBSITE,
    ).publish(deal, now=NOW)

    stored = rows_for(repository, deal.product.product_id)
    repository.close()

    assert result.success is False
    assert result.status == STATUS_PUBLICATION_ERROR
    assert result.reason == INVALID_REASON
    # T4: nothing was published, the attempt leaves no row behind
    assert stored == []


def test_service_keeps_reconciliation_when_publisher_raises(
    tmp_path,
):
    class ExplodingPublisher(WebsitePublisher):
        def publish(self, deal):
            raise RuntimeError("boom")

    repository = PublicationRepository(
        str(tmp_path / "website_exception.db")
    )
    deal = build_deal()

    result = PublicationService(
        publisher=ExplodingPublisher(),
        repository=repository,
        channel=CHANNEL_WEBSITE,
    ).publish(deal, now=NOW)

    stored = rows_for(repository, deal.product.product_id)
    repository.close()

    # T6: the outcome is unknown, so the row is kept
    assert result.success is False
    assert result.status == STATUS_PUBLICATION_EXCEPTION
    assert result.indeterminate is True
    assert stored == [
        (STATUS_RECONCILIATION, CHANNEL_WEBSITE, None)
    ]


def test_publisher_writes_nothing_to_disk(tmp_path, monkeypatch):
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    repository = PublicationRepository(
        str(tmp_path / "website_files.db")
    )
    deal = build_deal()

    result = PublicationService(
        publisher=WebsitePublisher(),
        repository=repository,
        channel=CHANNEL_WEBSITE,
    ).publish(deal, now=NOW)

    repository.close()

    assert result.success is True
    # spec 18.1: the site is materialised by the export job, the
    # publisher touches no file
    assert list(workdir.iterdir()) == []