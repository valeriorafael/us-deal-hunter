"""Static security/structure checks for the M2-A site shell.

These tests are intentionally minimal and non-fragile: they pin the
security and GitHub Pages requirements of the static shell
(``site/index.html`` + ``site/assets/style.css``) without asserting
class counts, CSS ordering or presentation details.

No Node, no browser, no extra dependencies: Python stdlib only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.services.site_export import validate_document

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
INDEX = SITE / "index.html"
STYLES = SITE / "assets" / "style.css"
DEALS = SITE / "deals.json"


def read_html() -> str:
    return INDEX.read_text(encoding="utf-8")


def read_css() -> str:
    return STYLES.read_text(encoding="utf-8")


def test_index_html_exists() -> None:
    assert INDEX.is_file()


def test_style_css_exists() -> None:
    assert STYLES.is_file()


def test_stylesheet_is_referenced_with_relative_path() -> None:
    assert 'href="assets/style.css"' in read_html()


def test_no_absolute_paths() -> None:
    html = read_html()

    assert re.search(r'''["']/''', html) is None


def test_no_jinja_tokens() -> None:
    html = read_html()

    assert "{{" not in html
    assert "{%" not in html


def test_no_inline_scripts_or_styles() -> None:
    html = read_html()

    # External relative scripts (assets/app.js, M2-B) are allowed;
    # inline scripts are not.
    for tag in re.findall(r"<script\b[^>]*>", html, re.I):
        assert "src=" in tag

    assert 'style="' not in html


def test_csp_meta_allows_only_local_resources() -> None:
    html = read_html()

    match = re.search(
        r'<meta[^>]*http-equiv="Content-Security-Policy"[^>]*'
        r'content="([^"]*)"',
        html,
    )

    assert match is not None, "CSP meta tag missing"

    csp = match.group(1)

    assert "script-src 'self'" in csp
    assert "style-src 'self'" in csp
    assert "img-src https:" in csp
    assert "connect-src 'self'" in csp


def test_no_hardcoded_external_urls() -> None:
    html = read_html()

    assert re.search(r"https?://", html) is None
    assert re.search(r"amazon\.", html, re.I) is None


def test_no_obvious_secrets() -> None:
    for text in (read_html(), read_css()):
        assert (
            re.search(
                r"token|secret|api[_-]?key|password|credential",
                text,
                re.I,
            )
            is None
        )
        assert (
            re.search(r"[0-9]{6,}:[A-Za-z0-9_-]{20,}", text) is None
        )


def test_amazon_associates_disclaimer() -> None:
    assert re.search(
        r"amazon associate", read_html(), re.I
    ) is not None


def test_main_landmarks_and_headings() -> None:
    html = read_html().lower()

    for landmark in ("<header", "<main", "<footer", "<h1", "<h2"):
        assert landmark in html


def test_states_are_markup_ready() -> None:
    html = read_html()

    for state_id in (
        "state-loading",
        "state-error",
        "state-empty",
    ):
        assert f'id="{state_id}"' in html
        assert 'role="status"' in html
        assert 'aria-live="polite"' in html

    loading = re.search(
        r'<p[^>]*id="state-loading"[^>]*>', html
    )
    assert loading is not None
    assert "hidden" not in loading.group(0)

    for state_id in ("state-error", "state-empty"):
        tag = re.search(rf'<p[^>]*id="{state_id}"[^>]*>', html)
        assert tag is not None
        assert "hidden" in tag.group(0)


def test_shell_meta_basics() -> None:
    html = read_html()

    assert html.lstrip().lower().startswith("<!doctype html>")
    assert '<html lang="en">' in html
    assert '<meta charset="utf-8">' in html
    assert 'name="viewport"' in html


def test_critical_text_colors_meet_wcag_aa() -> None:
    """Contrast fixes from the M2-E audit (measured ratios).

    Essential text previously failed WCAG AA (4.5:1):
    footer #9ca3af on white = 2.54; state #6b7280 on #f4f5f7 =
    4.43; badge #6b7280 on #f3f4f6 = 4.39; badge-score #2563eb
    on #dbeafe = 4.24. Replacements: 4.83, 6.93, 6.87, 5.49.
    """
    css = read_css()

    assert "#9ca3af" not in css
    assert "--muted-strong: #4b5563" in css

    for selector in (r"\.state \{", r"\.badge \{"):
        block = re.search(rf"{selector}[^}}]*\}}", css)
        assert block is not None
        assert "var(--muted-strong)" in block.group(0)

    score_badge = re.search(r"\.badge-score \{[^}]*\}", css)
    assert score_badge is not None
    assert "#1d4ed8" in score_badge.group(0)

    footer = re.search(r"\.site-footer \.container \{[^}]*\}", css)
    assert footer is not None
    assert "var(--muted)" in footer.group(0)


def test_deals_json_still_matches_contract() -> None:
    document = json.loads(DEALS.read_text(encoding="utf-8"))

    validate_document(document)
