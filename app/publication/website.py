"""Website publisher for the static GitHub Pages site (spec 18).

The public site is materialised from the database by
``export_site.py``/``site_export.py`` (spec 18.1); this publisher
carries no rendering, no file and no network responsibility.

Spec 18.3: the publication decision stays in ``PublicationService``
(validation, cooldown, attempt rows), the website publisher only
materialises offers that were already approved. It therefore does
nothing beyond accepting a deal whose affiliate URL can be shown on
the site and reporting a fixed, sanitized reason when it cannot
(spec 18.2 never publishes credentials or internals - the URL is
never echoed).
"""

from app.models.deal import Deal
from app.publication.base import (
    STATUS_PUBLISHED,
    STATUS_PUBLICATION_ERROR,
    PublicationResult,
    Publisher,
)


class WebsitePublisher(Publisher):
    """Publishes approved deals to the static website (spec 18.3).

    Stateless and deliberately minimal: no retry, no credentials,
    no deduplication of its own and no persistence. Every attempt
    is owned by PublicationService, which is also what keeps the
    24h cooldown per channel (spec 2.2).
    """

    def publish(self, deal: Deal) -> PublicationResult:
        url = deal.product.affiliate_url

        # same predicate the site export applies to a stored deal
        if isinstance(url, str) and url.startswith("http"):
            return PublicationResult(
                success=True,
                status=STATUS_PUBLISHED,
                reason="Deal published successfully.",
                message_id=None,
            )

        # spec 18.2: the reason is a fixed literal, the URL (which
        # may carry a tracking token) never leaves this module
        return PublicationResult(
            success=False,
            status=STATUS_PUBLICATION_ERROR,
            reason="Invalid affiliate URL.",
        )