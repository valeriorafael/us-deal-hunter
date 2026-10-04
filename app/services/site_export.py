"""Public site export contract (spec 18 / Fase 5 / M1).

Transforms already-approved publication rows into the public JSON
document consumed by the static site:

    SQLite -> export_site.py -> site/deals.json

Design rules (spec 18.1-18.2, 48):

* pure functions for transformation and serialization;
* explicit field whitelist -- never ``vars()``, ``asdict()`` or a
  whole-row dump;
* no Flask, no Telegram, no ``os.environ`` access;
* no scoring, discovery or business rules: this module only
  projects fields that already exist in the database.

Currency: publication rows do not store a currency column; the
whole product is the US market, whose currency is USD (the
``Product`` default).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

EXPORT_VERSION = 1
DEFAULT_CURRENCY = "USD"

# Presentation window for the exported price history: at most the
# last 90 days and at most 30 points, oldest first.
HISTORY_WINDOW_DAYS = 90
HISTORY_MAX_POINTS = 30

DOCUMENT_KEYS = frozenset(
    {
        "version",
        "generated_at",
        "deals",
    }
)

DEAL_KEYS = frozenset(
    {
        "id",
        "title",
        "price",
        "currency",
        "previous_price",
        "discount_pct",
        "score",
        "label",
        "image",
        "url",
        "published_at",
        "source_query",
        "history",
    }
)

HISTORY_POINT_KEYS = frozenset({"date", "price"})

_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
)
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class SitePublication:
    """Whitelisted projection of one ``publications`` row.

    Field names mirror the persisted columns; ``channel`` is not
    projected because the export only receives WEBSITE rows.
    """

    product_id: str
    title: str | None
    price: float
    published_at: datetime
    affiliate_url: str
    score: float | None
    label: str | None
    discount_vs_30d: float | None
    source_query: str | None
    image_url: str | None = None


@dataclass(frozen=True)
class SiteHistoryPoint:
    """One ``price_history`` row (whitelisted projection)."""

    price: float
    recorded_at: datetime


def _as_utc(value: datetime) -> datetime:
    """Aware UTC instant for comparison.

    Rows are stored with ``datetime.now().isoformat()`` (naive
    local time); naive inputs are interpreted as local time the
    same way Python's ``astimezone()`` does.
    """
    if value.tzinfo is None:
        return value.astimezone(timezone.utc)

    return value.astimezone(timezone.utc)


def utc_stamp(value: datetime) -> str:
    """ISO-8601 UTC second precision with a ``Z`` suffix."""
    stamped = _as_utc(value).replace(microsecond=0)

    return stamped.isoformat().replace("+00:00", "Z")


def _rounded(value: float) -> float:
    return round(float(value), 2)


def _discount_percent(discount_vs_30d: float | None) -> int | None:
    if discount_vs_30d is None:
        return None

    return int(round(discount_vs_30d * 100))


def _public_score(score: float | None) -> float | None:
    # Same presentation precedent as DealMessageFormatter: a score
    # of 0 means "not computed" (curated offers), so it is not
    # published as a number.
    if score is None or score <= 0:
        return None

    return float(score)


def _site_image_url(image_url: str | None) -> str | None:
    """Absolute http(s) image URL, or ``null``.

    The renderer only paints an ``<img>`` for an https URL and
    falls back to its emoji placeholder otherwise, so anything
    that is not a usable absolute URL is dropped here instead of
    reaching the document.
    """
    if not isinstance(image_url, str):
        return None

    image_url = image_url.strip()

    if not image_url.startswith(("http://", "https://")):
        return None

    return image_url


def _previous_price(
    history: Sequence[SiteHistoryPoint],
    published_at: datetime,
) -> float | None:
    """Most recent history price recorded before the publication."""
    published_instant = _as_utc(published_at)

    older = [
        point
        for point in history
        if _as_utc(point.recorded_at) < published_instant
    ]

    if not older:
        return None

    latest = max(older, key=lambda point: point.recorded_at)

    return _rounded(latest.price)


def _windowed_history(
    history: Sequence[SiteHistoryPoint],
    generated_at: datetime,
) -> list[dict]:
    cutoff = _as_utc(generated_at) - timedelta(
        days=HISTORY_WINDOW_DAYS
    )

    recent = [
        point
        for point in history
        if _as_utc(point.recorded_at) >= cutoff
    ]

    recent.sort(key=lambda point: point.recorded_at, reverse=True)
    kept = recent[:HISTORY_MAX_POINTS]
    kept.reverse()

    return [
        {
            "date": point.recorded_at.date().isoformat(),
            "price": _rounded(point.price),
        }
        for point in kept
    ]


def _latest_publication_per_product(
    publications: Iterable[SitePublication],
) -> list[SitePublication]:
    """Newest PUBLISHED row per product (the site lists each
    product once)."""
    ordered = sorted(
        publications,
        key=lambda item: (
            _as_utc(item.published_at),
            item.product_id,
        ),
        reverse=True,
    )

    latest: dict[str, SitePublication] = {}

    for item in ordered:
        if item.product_id not in latest:
            latest[item.product_id] = item

    return sorted(
        latest.values(),
        key=lambda item: _as_utc(item.published_at),
        reverse=True,
    )


def build_document(
    publications: Iterable[SitePublication],
    histories: Mapping[str, Sequence[SiteHistoryPoint]],
    *,
    generated_at: datetime,
) -> dict:
    """Pure builder of the public document (contract v1)."""
    deals = []

    for item in _latest_publication_per_product(
        publications
    ):
        history = histories.get(item.product_id, ())

        deals.append(
            {
                "id": item.product_id,
                "title": item.title or "",
                "price": _rounded(item.price),
                "currency": DEFAULT_CURRENCY,
                "previous_price": _previous_price(
                    history,
                    item.published_at,
                ),
                "discount_pct": _discount_percent(
                    item.discount_vs_30d
                ),
                "score": _public_score(item.score),
                "label": item.label,
                "image": _site_image_url(item.image_url),
                "url": item.affiliate_url,
                "published_at": utc_stamp(item.published_at),
                "source_query": item.source_query,
                "history": _windowed_history(
                    history,
                    generated_at,
                ),
            }
        )

    return {
        "version": EXPORT_VERSION,
        "generated_at": utc_stamp(generated_at),
        "deals": deals,
    }


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(
        value, bool
    )


def _validate_history_point(
    point: object,
    where: str,
) -> None:
    if not isinstance(point, dict):
        raise ValueError(f"{where} must be an object")

    if frozenset(point) != HISTORY_POINT_KEYS:
        raise ValueError(
            f"{where} keys must be {sorted(HISTORY_POINT_KEYS)}"
        )

    date = point["date"]

    if not isinstance(date, str) or not _DATE_PATTERN.match(
        date
    ):
        raise ValueError(
            f"{where}.date must be YYYY-MM-DD"
        )

    if not _is_number(point["price"]) or point["price"] <= 0:
        raise ValueError(
            f"{where}.price must be a positive number"
        )


def _validate_deal(deal: object, index: int) -> None:
    where = f"deals[{index}]"

    if not isinstance(deal, dict):
        raise ValueError(f"{where} must be an object")

    if frozenset(deal) != DEAL_KEYS:
        raise ValueError(
            f"{where} keys must be exactly {sorted(DEAL_KEYS)}"
        )

    if not isinstance(deal["id"], str) or not deal["id"]:
        raise ValueError(f"{where}.id must be a string")

    if not isinstance(deal["title"], str):
        raise ValueError(f"{where}.title must be a string")

    if (
        not _is_number(deal["price"])
        or deal["price"] <= 0
    ):
        raise ValueError(
            f"{where}.price must be a positive number"
        )

    if deal["currency"] != DEFAULT_CURRENCY:
        raise ValueError(
            f"{where}.currency must be {DEFAULT_CURRENCY!r}"
        )

    previous = deal["previous_price"]

    if previous is not None and (
        not _is_number(previous) or previous <= 0
    ):
        raise ValueError(
            f"{where}.previous_price must be null or a "
            "positive number"
        )

    discount = deal["discount_pct"]

    if discount is not None and not (
        isinstance(discount, int)
        and not isinstance(discount, bool)
    ):
        raise ValueError(
            f"{where}.discount_pct must be null or an integer"
        )

    if deal["score"] is not None and not _is_number(
        deal["score"]
    ):
        raise ValueError(
            f"{where}.score must be null or a number"
        )

    if deal["label"] is not None and not isinstance(
        deal["label"], str
    ):
        raise ValueError(
            f"{where}.label must be null or a string"
        )

    if deal["image"] is not None and (
        not isinstance(deal["image"], str)
        or not deal["image"].startswith("http")
    ):
        raise ValueError(
            f"{where}.image must be null or an http(s) URL"
        )

    if not isinstance(deal["url"], str) or not deal[
        "url"
    ].startswith("http"):
        raise ValueError(
            f"{where}.url must be an http(s) URL"
        )

    if not isinstance(deal["published_at"], str) or not (
        _TIMESTAMP_PATTERN.match(deal["published_at"])
    ):
        raise ValueError(
            f"{where}.published_at must be an ISO-8601 "
            "UTC timestamp ending in Z"
        )

    if deal["source_query"] is not None and not isinstance(
        deal["source_query"], str
    ):
        raise ValueError(
            f"{where}.source_query must be null or a string"
        )

    history = deal["history"]

    if not isinstance(history, list):
        raise ValueError(f"{where}.history must be a list")

    if len(history) > HISTORY_MAX_POINTS:
        raise ValueError(
            f"{where}.history has more than "
            f"{HISTORY_MAX_POINTS} points"
        )

    for offset, point in enumerate(history):
        _validate_history_point(
            point,
            f"{where}.history[{offset}]",
        )


def validate_document(document: object) -> None:
    """Raise ``ValueError`` unless the document matches the
    public contract exactly (whitelist enforcement)."""
    if not isinstance(document, dict):
        raise ValueError("document must be an object")

    if frozenset(document) != DOCUMENT_KEYS:
        raise ValueError(
            f"document keys must be exactly "
            f"{sorted(DOCUMENT_KEYS)}"
        )

    if document["version"] != EXPORT_VERSION:
        raise ValueError(
            f"version must be {EXPORT_VERSION}"
        )

    generated_at = document["generated_at"]

    if not isinstance(generated_at, str) or not (
        _TIMESTAMP_PATTERN.match(generated_at)
    ):
        raise ValueError(
            "generated_at must be an ISO-8601 UTC "
            "timestamp ending in Z"
        )

    deals = document["deals"]

    if not isinstance(deals, list):
        raise ValueError("deals must be a list")

    for index, deal in enumerate(deals):
        _validate_deal(deal, index)


def serialize_document(document: dict) -> str:
    """UTF-8 JSON text for the public document."""
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def write_document_atomic(
    path: str | Path,
    document: dict,
) -> None:
    """Validate, serialize and atomically replace ``path``.

    The previous file is only replaced after the temporary file
    has been written and reloaded successfully; on any failure no
    partial file is left behind.
    """
    validate_document(document)

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    temporary = target.with_name(target.name + ".tmp")

    try:
        with open(
            temporary,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as handle:
            handle.write(serialize_document(document))
            handle.flush()
            os.fsync(handle.fileno())

        reloaded = json.loads(
            temporary.read_text(encoding="utf-8")
        )

        validate_document(reloaded)

        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)

        raise
