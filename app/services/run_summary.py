"""Operational summaries and error sanitization (Phase 3).

Error messages can carry integration details (URLs with tokens,
credentials in query strings). Nothing from an exception reaches
the console or the run summary before passing through
``sanitize_error``.
"""

from dataclasses import dataclass
import re

DEFAULT_ERROR_LIMIT = 300

_SECRET_PARAMETER = re.compile(
    r"(?i)\b([A-Za-z0-9_-]*"
    r"(?:token|secret|key|password))=[^&\s'\"]+"
)

_TELEGRAM_BOT_PATH = re.compile(r"/bot[^/\s]+/")

# A bare bot token ("<digits>:<secret>") that never went through a
# URL, e.g. copied out of a description or an exception message.
_BARE_BOT_TOKEN = re.compile(r"\d{6,}:[A-Za-z0-9_-]{20,}")


def sanitize_text(
    text: str,
    limit: int = DEFAULT_ERROR_LIMIT,
) -> str:
    """Mask secret-shaped content in ``text`` and truncate it."""
    message = _SECRET_PARAMETER.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        text,
    )
    message = _TELEGRAM_BOT_PATH.sub(
        "/bot[REDACTED]/",
        message,
    )
    message = _BARE_BOT_TOKEN.sub("[REDACTED]", message)

    if len(message) > limit:
        message = message[:limit]

    return message


def sanitize_error(
    exc: BaseException,
    limit: int = DEFAULT_ERROR_LIMIT,
) -> str:
    """Render ``exc`` as ``TypeName: message`` without secrets.

    Known secret-shaped parameters are replaced by REDACTED and
    Telegram bot tokens hidden inside URLs are masked. The result
    is truncated to ``limit`` characters.
    """
    return sanitize_text(
        f"{type(exc).__name__}: {exc}",
        limit,
    )


DEFAULT_ERROR_LIST_LIMIT = 10
SUMMARY_SEPARATOR = "========================================"


@dataclass(frozen=True)
class KeywordOutcome:
    """Result of one keyword inside a run (spec phase 3, section 9)."""

    query: str
    status: str  # "OK" | "FAILED" | "SKIPPED"
    deals_found: int
    error: str | None


@dataclass
class RunSummary:
    """Aggregated view of one run, rendered by ``lines()``.

    The rendered text is the exact SUMMARY block of section 10;
    ``errors`` is capped at DEFAULT_ERROR_LIST_LIMIT visible
    lines followed by a ``+N more`` line.
    """

    keyword_outcomes: list[KeywordOutcome]
    deals_found: int
    publications_attempted: int
    publications_successful: int
    publications_failed: int
    duplicates_blocked: int
    reconciled: int
    deadline_exceeded: bool
    errors: list[str]
    publication_limit: int = 0
    # Phase 4: attempts recovered by probing the channel. Reported
    # next to reconciliation so both sides of the at-least-once
    # recovery are visible in one run (deliberate phase 4 addition
    # to the section 10 format).
    channel_verified: int = 0

    def lines(self) -> list[str]:
        processed = len(self.keyword_outcomes)
        failed = sum(
            1
            for outcome in self.keyword_outcomes
            if outcome.status == "FAILED"
        )
        skipped = sum(
            1
            for outcome in self.keyword_outcomes
            if outcome.status == "SKIPPED"
        )

        lines = [
            SUMMARY_SEPARATOR,
            "SUMMARY",
            SUMMARY_SEPARATOR,
            f"Keywords processed: {processed}",
            f"Keywords failed: {failed}",
            f"Keywords skipped: {skipped}",
            f"Deals found: {self.deals_found}",
            f"Publication limit: {self.publication_limit}",
            f"Publications attempted: "
            f"{self.publications_attempted}",
            f"Publications successful: "
            f"{self.publications_successful}",
            f"Publications failed: "
            f"{self.publications_failed}",
            f"Duplicates blocked: {self.duplicates_blocked}",
            f"Reconciled unknown: {self.reconciled}",
            f"Channel verified: {self.channel_verified}",
            f"Deadline exceeded: "
            f"{'yes' if self.deadline_exceeded else 'no'}",
            f"Errors ({len(self.errors)}):",
        ]

        visible = self.errors[:DEFAULT_ERROR_LIST_LIMIT]
        lines.extend(f"  - {error}" for error in visible)

        if len(self.errors) > DEFAULT_ERROR_LIST_LIMIT:
            hidden = len(self.errors) - DEFAULT_ERROR_LIST_LIMIT
            lines.append(f"  - +{hidden} more")

        return lines
