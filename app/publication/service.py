import logging
from datetime import datetime, timedelta

from app.deals.validator import DealValidator
from app.models.deal import Deal
from app.publication.base import (
    CHANNEL_TELEGRAM,
    DEFAULT_PUBLICATION_COOLDOWN,
    STATUS_DUPLICATE_PUBLICATION,
    STATUS_PUBLICATION_EXCEPTION,
    STATUS_PUBLICATION_STORE_ERROR,
    PublicationResult,
    Publisher,
    Verdict,
)
from app.services.publication_repository import (
    AttemptRecord,
    PublicationRepository,
)
from app.services.resilience import (
    CHANNEL_VERIFY_MAX_AGE_SECONDS,
    CHANNEL_VERIFY_MAX_PER_RUN,
    STALE_ATTEMPT_SECONDS,
)
from app.services.run_summary import sanitize_error

logger = logging.getLogger(__name__)


class PublicationService:
    """
    Coordinates deal validation, deduplication and publication.

    Deal
        -> validation
        -> atomic duplicate check + attempt row (PENDING)
        -> SENDING
        -> publisher
        -> PUBLISHED / delete / RECONCILIATION
        -> channel verification (phase 4)

    Invariant: the publisher is never invoked without a committed
    PENDING row (fail-closed), and only PUBLISHED rows take part
    in the cooldown check.
    """

    def __init__(
        self,
        publisher: Publisher,
        deal_validator: DealValidator | None = None,
        repository: PublicationRepository | None = None,
        cooldown: timedelta | None = (
            DEFAULT_PUBLICATION_COOLDOWN
        ),
        *,
        verifier=None,
        channel: str = CHANNEL_TELEGRAM,
    ):
        self.publisher = publisher
        self.deal_validator = (
            deal_validator or DealValidator()
        )
        self.repository = (
            repository or PublicationRepository()
        )
        self.cooldown = cooldown
        # optional MessageVerifier: probes the channel for
        # attempts whose outcome was never recorded (phase 4)
        self.verifier = verifier
        # publication channel: one service instance per channel,
        # single shared pipeline (spec 2.2/50)
        self.channel = channel

    def _duplicate_result(self) -> PublicationResult:
        if self.cooldown is None:
            reason = "Product was already published."
        else:
            reason = "Product was published recently."

        return PublicationResult(
            success=False,
            status=STATUS_DUPLICATE_PUBLICATION,
            reason=reason,
        )

    def _is_duplicate(
        self,
        deal: Deal,
        now: datetime,
    ) -> bool:
        if self.cooldown is None:
            return self.repository.was_published(
                product_id=deal.product.product_id,
                channel=self.channel,
            )

        return self.repository.was_published_recently(
            product_id=deal.product.product_id,
            now=now,
            cooldown=self.cooldown,
            channel=self.channel,
        )

    def _store_error(self, exc: Exception) -> PublicationResult:
        logger.error(
            "publication store failure: %s",
            sanitize_error(exc),
        )

        return PublicationResult(
            success=False,
            status=STATUS_PUBLICATION_STORE_ERROR,
            reason=sanitize_error(exc),
        )

    def _discard_attempt_quietly(
        self,
        attempt_id: int,
    ) -> None:
        """Best effort delete of an attempt that never sent.

        If the delete fails the row stays behind and is resolved
        by reconcile_stale_attempts later; it never blocks the
        cooldown.
        """
        try:
            self.repository.drop_attempt(attempt_id)
        except Exception as exc:
            logger.error(
                "could not drop attempt %s: %s",
                attempt_id,
                sanitize_error(exc),
            )

    def _store_unknown_quietly(self, attempt_id: int) -> None:
        try:
            self.repository.mark_unknown(attempt_id)
        except Exception as exc:
            logger.error(
                "could not mark attempt %s unknown: %s",
                attempt_id,
                sanitize_error(exc),
            )

    def reconcile_stale_attempts(
        self,
        now: datetime | None = None,
    ) -> int:
        """Resolve PENDING/SENDING rows orphaned by a crash.

        Rows younger than STALE_ATTEMPT_SECONDS are left alone
        because they may belong to a run that is still active.
        """
        now = now or datetime.now()

        return self.repository.reconcile_stale_attempts(
            older_than=now
            - timedelta(seconds=STALE_ATTEMPT_SECONDS)
        )

    def verify_channel_attempts(
        self,
        now: datetime | None = None,
    ) -> int:
        """Probe in-flight attempts against the channel (phase 4).

        Runs before reconciliation: a message the channel still
        has is promoted to PUBLISHED keeping its original send
        time (the cooldown counts from the real attempt), one
        Telegram explicitly reports as deleted is dropped, and
        anything else stays untouched for the next run (A-4).
        """
        if self.verifier is None:
            return 0

        verify = getattr(self.verifier, "verify_message", None)

        if verify is None:
            return 0

        now = now or datetime.now()

        records = self.repository.attempts_for_verification(
            stale_before=(
                now - timedelta(seconds=STALE_ATTEMPT_SECONDS)
            ),
            not_older_than=(
                now
                - timedelta(
                    seconds=CHANNEL_VERIFY_MAX_AGE_SECONDS
                )
            ),
            limit=CHANNEL_VERIFY_MAX_PER_RUN,
            channel=self.channel,
        )

        resolved = 0

        for record in records:
            try:
                verdict = verify(
                    record.message_id,
                    affiliate_url=record.affiliate_url,
                )
            except Exception as exc:
                # a failing probe never blocks the run
                logger.error(
                    "channel verification failed for attempt "
                    "%s: %s",
                    record.attempt_id,
                    sanitize_error(exc),
                )
                continue

            if not isinstance(verdict, Verdict):
                logger.warning(
                    "channel verification returned %r for "
                    "attempt %s",
                    verdict,
                    record.attempt_id,
                )
                continue

            if verdict is Verdict.EXISTS:
                resolved += self._store_verified(
                    record
                )
            elif verdict is Verdict.ABSENT:
                resolved += self._drop_absent(record)
            else:
                logger.debug(
                    "attempt %s stays for reconciliation "
                    "(verdict=UNKNOWN)",
                    record.attempt_id,
                )

        return resolved

    def _store_verified(self, record: AttemptRecord) -> int:
        try:
            self.repository.mark_published(
                record.attempt_id,
                record.published_at,
                message_id=record.message_id,
            )
        except Exception as exc:
            logger.error(
                "could not persist verified publication %s: %s",
                record.attempt_id,
                sanitize_error(exc),
            )
            return 0

        logger.info(
            "verified in the channel attempt=%s "
            "message_id=%s",
            record.attempt_id,
            record.message_id,
        )

        return 1

    def _drop_absent(self, record: AttemptRecord) -> int:
        try:
            self.repository.drop_attempt(record.attempt_id)
        except Exception as exc:
            logger.error(
                "could not drop absent attempt %s: %s",
                record.attempt_id,
                sanitize_error(exc),
            )
            return 0

        logger.info(
            "verified absent attempt=%s message_id=%s",
            record.attempt_id,
            record.message_id,
        )

        return 1

    def publish(
        self,
        deal: Deal,
        now: datetime | None = None,
    ) -> PublicationResult:
        now = now or datetime.now()

        validation = self.deal_validator.validate(deal)

        if not validation.is_valid:
            return PublicationResult(
                success=False,
                status=validation.status,
                reason=validation.reason,
            )

        # T1: the duplicate check and the intent commit share one
        # write transaction (H1), so a concurrent run can never
        # insert a second attempt for the same product
        try:
            attempt_id = (
                self.repository.begin_attempt_exclusive(
                    duplicate_check=lambda: (
                        self._is_duplicate(deal, now)
                        or self.repository.has_inflight_attempt(
                            deal.product.product_id,
                            channel=self.channel,
                        )
                    ),
                    product_id=deal.product.product_id,
                    affiliate_url=deal.product.affiliate_url,
                    price=deal.product.current_price,
                    attempted_at=now,
                    title=deal.product.title,
                    score=deal.score,
                    label=deal.label,
                    discount_vs_30d=deal.discount_vs_30d,
                    source_query=deal.source_query,
                    channel=self.channel,
                )
            )
        except Exception as exc:
            # T8: no row, so nothing may be sent
            return self._store_error(exc)

        if attempt_id is None:
            return self._duplicate_result()

        # T2: committed right before the publisher runs
        try:
            self.repository.mark_sending(attempt_id)
        except Exception as exc:
            self._discard_attempt_quietly(attempt_id)

            return self._store_error(exc)

        try:
            result = self.publisher.publish(deal)
        except Exception as exc:
            # T6: outcome unknown
            self._store_unknown_quietly(attempt_id)
            logger.error(
                "publisher raised for %s: %s",
                deal.product.product_id,
                sanitize_error(exc),
            )

            return PublicationResult(
                success=False,
                status=STATUS_PUBLICATION_EXCEPTION,
                reason=sanitize_error(exc),
                indeterminate=True,
            )

        if result.success:
            # T3
            try:
                self.repository.mark_published(
                    attempt_id,
                    now,
                    message_id=result.message_id,
                )

                logger.info(
                    "publication stored for %s "
                    "message_id=%s",
                    deal.product.product_id,
                    result.message_id,
                )
            except Exception as exc:
                # the message was delivered; the row stays
                # SENDING and is reconciled on the next run
                logger.error(
                    "could not persist publication of %s: %s",
                    deal.product.product_id,
                    sanitize_error(exc),
                )

            return result

        if result.indeterminate:
            # T5
            self._store_unknown_quietly(attempt_id)

            return result

        # T4: known failure, nothing was published
        self._discard_attempt_quietly(attempt_id)

        return result
