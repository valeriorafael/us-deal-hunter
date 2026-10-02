from app.services.run_summary import (
    DEFAULT_ERROR_LIMIT,
    sanitize_error,
    sanitize_text,
)


def test_sanitize_error_includes_exception_type():
    message = sanitize_error(ValueError("bad input"))

    assert message == "ValueError: bad input"


def test_sanitize_error_redacts_secret_parameters():
    message = sanitize_error(
        ValueError(
            "request failed for "
            "https://example.com/?token=abc123&x=1 "
            "api_key=XYZ secret=shh password=hunter2"
        )
    )

    assert "abc123" not in message
    assert "XYZ" not in message
    assert "shh" not in message
    assert "hunter2" not in message
    assert "token=[REDACTED]" in message
    assert "api_key=[REDACTED]" in message
    assert "secret=[REDACTED]" in message
    assert "password=[REDACTED]" in message
    assert "x=1" in message


def test_sanitize_error_keeps_ordinary_keywords():
    message = sanitize_error(
        ValueError("keywords=wireless mouse failed")
    )

    assert "keywords=wireless mouse" in message


def test_sanitize_error_masks_telegram_bot_path():
    message = sanitize_error(
        RuntimeError(
            "Max retries exceeded with url: "
            "/bot123456:ABC-DEF/sendMessage"
        )
    )

    assert "123456:ABC-DEF" not in message
    assert "/bot[REDACTED]/sendMessage" in message


def test_sanitize_error_truncates_to_default_limit():
    message = sanitize_error(ValueError("x" * 1000))

    assert len(message) == DEFAULT_ERROR_LIMIT == 300


def test_sanitize_error_honours_custom_limit():
    message = sanitize_error(
        ValueError("y" * 100), limit=10
    )

    assert len(message) == 10


def test_sanitize_text_applies_same_protection():
    message = sanitize_text(
        "TELEGRAM_REQUEST_ERROR - see ?token=abc"
    )

    assert "abc" not in message
    assert "token=[REDACTED]" in message


def test_sanitize_error_masks_bare_bot_token():
    message = sanitize_error(
        RuntimeError(
            "telegram rejected 123456:AAHz7Kd9xL2mNpQr4sTvWxYz1234567890"
        )
    )

    assert "123456:AAHz7Kd9xL2mNpQr4sTvWxYz1234567890" not in message
    assert "[REDACTED]" in message


def test_sanitize_text_truncates():
    assert sanitize_text("z" * 500, limit=5) == "zzzzz"


from app.services.run_summary import (
    KeywordOutcome,
    RunSummary,
    SUMMARY_SEPARATOR,
)


def build_summary(**overrides):
    values = {
        "keyword_outcomes": [
            KeywordOutcome("mouse", "OK", 4, None),
            KeywordOutcome("keyboard", "FAILED", 0, "e"),
            KeywordOutcome("pad", "OK", 3, None),
        ],
        "deals_found": 7,
        "publications_attempted": 5,
        "publications_successful": 2,
        "publications_failed": 3,
        "duplicates_blocked": 1,
        "reconciled": 0,
        "deadline_exceeded": False,
        "errors": [
            "keyword: keyboard: TimeoutError: boom",
            "publication: B08: RuntimeError: nope",
        ],
        "publication_limit": 3,
    }
    values.update(overrides)

    return RunSummary(**values)


def test_summary_lines_match_spec_format():
    lines = build_summary().lines()

    assert lines == [
        SUMMARY_SEPARATOR,
        "SUMMARY",
        SUMMARY_SEPARATOR,
        "Keywords processed: 3",
        "Keywords failed: 1",
        "Keywords skipped: 0",
        "Deals found: 7",
        "Publication limit: 3",
        "Publications attempted: 5",
        "Publications successful: 2",
        "Publications failed: 3",
        "Duplicates blocked: 1",
        "Reconciled unknown: 0",
        # phase 4 extension of the section 10 format (A-3)
        "Channel verified: 0",
        "Deadline exceeded: no",
        "Errors (2):",
        "  - keyword: keyboard: TimeoutError: boom",
        "  - publication: B08: RuntimeError: nope",
    ]


def test_summary_counts_skipped_keywords():
    summary = build_summary(
        keyword_outcomes=[
            KeywordOutcome("a", "OK", 1, None),
            KeywordOutcome("b", "SKIPPED", 0, None),
            KeywordOutcome("c", "SKIPPED", 0, None),
            KeywordOutcome("d", "FAILED", 0, "x"),
        ],
        errors=["x"],
    )

    lines = summary.lines()

    assert "Keywords processed: 4" in lines
    assert "Keywords failed: 1" in lines
    assert "Keywords skipped: 2" in lines


def test_summary_declares_deadline_exceeded():
    lines = build_summary(deadline_exceeded=True).lines()

    assert "Deadline exceeded: yes" in lines


def test_summary_caps_error_list_at_ten():
    errors = [f"error {index}" for index in range(12)]
    summary = build_summary(errors=errors)

    lines = summary.lines()

    assert "Errors (12):" in lines
    assert "  - error 9" in lines
    assert "  - error 10" not in lines
    assert lines[-1] == "  - +2 more"


def test_summary_without_errors_still_prints_header():
    lines = build_summary(errors=[]).lines()

    assert "Errors (0):" in lines
    assert not any(
        line.startswith("  - ") for line in lines
    )
