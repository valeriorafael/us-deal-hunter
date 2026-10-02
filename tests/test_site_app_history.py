"""Static contract tests for the M2-D price-history renderer.

No Node in this project: app.js is analysed statically with
Python stdlib only. The tests pin the history contract (guard
clauses, copy-before-sort, cap of 5, pure presentation) and the
security rules, without asserting line counts or the textual
order of functions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.services.site_export import validate_document

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
APP = SITE / "assets" / "app.js"
DEALS = SITE / "deals.json"


def read_js() -> str:
    return APP.read_text(encoding="utf-8")


def test_handles_deal_history() -> None:
    js = read_js()

    assert "deal.history" in js
    assert "appendHistory" in js


def test_guards_history_with_array_is_array() -> None:
    js = read_js()

    assert "Array.isArray(deal.history)" in js
    assert "!Array.isArray(deal.history)" in js


def test_creates_history_section_and_list_via_create_element() -> None:
    js = read_js()

    assert 'createElement("section"' in js
    assert 'createElement("ul"' in js
    assert 'createElement("time"' in js


def test_history_values_enter_via_text_content() -> None:
    js = read_js()

    assert "textContent" in js
    assert "point.date" in js
    assert "point.price" in js


def test_shows_at_most_five_points() -> None:
    assert "slice(0, 5)" in read_js()


def test_does_not_mutate_original_history_array() -> None:
    js = read_js()

    assert "deal.history.slice()" in js
    assert "history.reverse()" not in js
    assert "deal.history.sort(" not in js


def test_empty_history_creates_no_section() -> None:
    js = read_js()

    assert "deal.history.length === 0" in js
    assert "No history" not in js
    assert "History unavailable" not in js


def test_null_or_missing_history_does_not_break_card() -> None:
    # The Array.isArray guard short-circuits for null/undefined/
    # non-arrays before anything touches the value.
    js = read_js()

    assert "!Array.isArray(deal.history)" in js


def test_formats_history_prices_with_intl() -> None:
    js = read_js()

    assert "Intl.NumberFormat" in js
    assert "formatPrice(point.price" in js


def test_history_prices_use_deal_currency() -> None:
    assert "deal.currency" in read_js()


def test_no_history_calculations() -> None:
    js = read_js()

    upper = js.upper()

    for word in (
        "AVERAGE",
        "VARIATION",
        "PERCENT",
        "SAVING",
        "TREND",
    ):
        assert word not in upper

    assert "* 100" not in js
    assert "reduce(" not in js


def test_no_html_injection_constructs() -> None:
    js = read_js()

    for forbidden in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "new Function",
    ):
        assert forbidden not in js


def test_no_external_urls() -> None:
    js = read_js()

    assert "http://" not in js
    assert "https://" not in js


def test_no_forbidden_keywords() -> None:
    js = read_js().upper()

    for forbidden in (
        "AMAZON.",
        "TELEGRAM",
        "BOT_TOKEN",
        "AWS_SECRET",
        "ACCESS_KEY",
        "PASSWORD",
    ):
        assert forbidden not in js


def test_deals_json_still_matches_contract() -> None:
    document = json.loads(DEALS.read_text(encoding="utf-8"))

    validate_document(document)


def test_no_html_string_literals_in_js() -> None:
    # Data (including history dates/prices) can only reach the DOM
    # through textContent / setAttribute: there is not a single
    # HTML tag literal in the script.
    assert re.search(r'''["']<[a-zA-Z]''', read_js()) is None
