"""Static contract tests for the M2-B loader (site/assets/app.js).

There is no Node in this project, so these tests analyse the
JavaScript statically with Python stdlib only. They pin the
behavioural contract of the loader (fetch path, HTTP handling,
minimal document validation, UI states) and the security rules
(no HTML string injection, no external URLs, no storage/tracking,
no secrets) without asserting line counts or function ordering.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.services.site_export import validate_document

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
INDEX = SITE / "index.html"
APP = SITE / "assets" / "app.js"
DEALS = SITE / "deals.json"


def read_js() -> str:
    return APP.read_text(encoding="utf-8")


def read_html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_app_js_exists() -> None:
    assert APP.is_file()


def test_index_references_app_js() -> None:
    assert 'src="assets/app.js"' in read_html()


def test_reference_is_relative() -> None:
    html = read_html()

    assert re.search(r'''["']/''', html) is None
    assert re.search(r'''src=["']https?://''', html) is None


def test_fetches_deals_json_relatively() -> None:
    assert 'fetch("./deals.json"' in read_js()


def test_checks_response_ok() -> None:
    assert "response.ok" in read_js()


def test_parses_json_response() -> None:
    assert "response.json()" in read_js()


def test_validates_document_version() -> None:
    js = read_js()

    assert "version !== 1" in js or "version === 1" in js


def test_validates_deals_is_array() -> None:
    js = read_js()

    assert "Array.isArray(" in js
    assert "deals" in js


def test_handles_empty_deals() -> None:
    js = read_js()

    assert "deals.length === 0" in js


def test_has_all_ui_states() -> None:
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


def test_no_dangerous_html_or_code_injection() -> None:
    js = read_js()

    for forbidden in (
        "innerHTML",
        "outerHTML",
        "document.write",
        "eval(",
        "new Function",
        "insertAdjacentHTML",
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
        "SECRET",
        "TOKEN",
    ):
        assert forbidden not in js


def test_no_storage_cookies_or_analytics() -> None:
    js = read_js()

    for forbidden in (
        "localStorage",
        "sessionStorage",
        "document.cookie",
        "analytics",
        "gtag",
    ):
        assert forbidden not in js


def test_no_external_imports() -> None:
    js = read_js()

    assert re.search(r"^\s*import\s", js, re.M) is None
    assert re.search(r"^\s*export\s", js, re.M) is None
    assert "require(" not in js


def test_deals_json_still_matches_contract() -> None:
    document = json.loads(DEALS.read_text(encoding="utf-8"))

    validate_document(document)
