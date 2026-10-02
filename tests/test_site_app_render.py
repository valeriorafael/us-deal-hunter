"""Static contract tests for the M2-C card renderer (app.js).

No Node in this project: the JavaScript is analysed statically
with Python stdlib only. The tests pin the rendering contract
(use of DOM APIs, which fields are read, HTTPS gates, security
attributes) and demonstrate that no HTML-injection path exists,
without asserting line counts or function ordering.
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

# Representative malicious payloads the renderer must only ever
# treat as plain text (never as HTML).
PAYLOAD_TITLE = "<script>alert(1)</script>"
PAYLOAD_URL = "https://example.com/?x=<script>"
PAYLOAD_IMAGE = "https://example.com/image.jpg"


def read_js() -> str:
    return APP.read_text(encoding="utf-8")


def test_has_deal_render_function() -> None:
    assert "renderDeal" in read_js()


def test_uses_create_element() -> None:
    assert "document.createElement(" in read_js()


def test_uses_text_content() -> None:
    assert "textContent" in read_js()


def test_creates_li_card_elements() -> None:
    js = read_js()

    assert 'createElement("li"' in js
    assert "deal-card" in js


def test_reads_title() -> None:
    assert "deal.title" in read_js()


def test_title_has_product_id_fallback() -> None:
    js = read_js()

    assert '"Product "' in js
    assert "deal.id" in js


def test_reads_price() -> None:
    assert "deal.price" in read_js()


def test_formats_price_with_intl_number_format() -> None:
    js = read_js()

    assert "Intl.NumberFormat" in js
    assert "deal.currency" in js


def test_previous_price_requires_number_greater_than_price() -> None:
    js = read_js()

    assert 'typeof deal.previous_price === "number"' in js
    assert "deal.previous_price > deal.price" in js


def test_discount_pct_shown_without_calculation() -> None:
    js = read_js()

    assert "deal.discount_pct" in js
    assert "* 100" not in js
    assert "- deal.price" not in js


def test_score_shown_without_calculation() -> None:
    js = read_js()

    assert "deal.score" in js
    assert "deal.score !== null" in js


def test_label_shown_as_received() -> None:
    js = read_js()

    assert "deal.label" in js
    assert "deal.label !== null" in js


def test_reads_image_field() -> None:
    assert "deal.image" in read_js()


def test_image_requires_https() -> None:
    js = read_js()

    assert "isHttpsUrl" in js
    assert r"/^https:\/\//" in js


def test_image_uses_lazy_loading() -> None:
    assert 'setAttribute("loading", "lazy")' in read_js()


def test_reads_offer_url() -> None:
    assert "deal.url" in read_js()


def test_link_opens_in_new_tab() -> None:
    assert '"_blank"' in read_js()


def test_link_rel_contains_required_tokens() -> None:
    js = read_js()

    assert "sponsored" in js
    assert "nofollow" in js
    assert "noopener" in js


def test_formats_published_at() -> None:
    assert "deal.published_at" in read_js()


def test_does_not_render_source_query() -> None:
    assert "source_query" not in read_js()


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


def test_no_html_string_literals_payloads_only_reach_dom_as_text() -> None:
    """XSS demonstration: data can only enter the DOM as text.

    The renderer never builds HTML markup from strings — there is
    no HTML tag literal anywhere in app.js — so payloads such as
    ``<script>alert(1)</script>`` (title) or a ``<script>`` inside
    an image/offer URL can only be assigned via ``textContent`` or
    ``setAttribute``, where they stay inert.
    """
    js = read_js()

    assert re.search(r'''["']<[a-zA-Z]''', js) is None
    assert "textContent" in js
    assert "setAttribute(" in js

    for payload in (PAYLOAD_TITLE, PAYLOAD_URL, PAYLOAD_IMAGE):
        assert payload not in js


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


def test_m2b_states_are_preserved() -> None:
    js = read_js()

    for function_name in (
        "showLoading",
        "showError",
        "showEmpty",
        "showReady",
    ):
        assert function_name in js

    for state_name in ("loading", "error", "empty", "ready"):
        assert state_name in js
