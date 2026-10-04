from html import escape

from app.models.deal import Deal

# Telegram titles are only part of the message, but an unbounded
# one makes the caption/text limits impossible to enforce (phase 4,
# item 3): the raw title is cut before escaping so the escaped
# length can never explode past it.
MAX_TITLE_LENGTH = 200


class DealMessageFormatter:
    """
    Formats a Deal into a Telegram-ready HTML message.
    """

    def format(self, deal: Deal) -> str:
        product = deal.product

        title = escape(
            product.title.strip()[:MAX_TITLE_LENGTH]
        )
        affiliate_url = escape(
            product.affiliate_url.strip(),
            quote=True,
        )

        lines = [
            "🔥 <b>DEAL FOUND</b>",
            "",
            f"<b>{title}</b>",
            "",
            f"💰 <b>${product.current_price:.2f}</b>",
        ]

        if deal.reference_discount is not None:
            lines.append(
                f"🏷 <b>{deal.reference_discount:.0%} OFF</b>"
            )

            lines.append(
                f"Was: <s>${deal.reference_price:.2f}</s>"
            )

        if deal.discount_vs_30d is not None:
            lines.append(
                f"📉 {deal.discount_vs_30d:.0%} below "
                "the 30-day average"
            )

        if product.lowest_price_90d is not None:
            lines.append(
                f"📊 Lowest price in 90d: "
                f"${product.lowest_price_90d:.2f}"
            )

        if product.rating is not None:
            lines.append(
                f"⭐ {product.rating:.1f}/5"
                f" ({product.review_count:,} reviews)"
            )

        if deal.score > 0:
            lines.append(
                f"🏷 <b>Score:</b> {deal.score:.0f}/100"
            )
        else:
            lines.append(
                "✅ <b>Verified deal</b>"
            )

        if deal.source_name:
            lines.append(
                f"🔎 Source: {escape(deal.source_name)}"
            )

        lines.extend(
            [
                "",
                f'👉 <a href="{affiliate_url}">VIEW DEAL</a>',
            ]
        )

        return "\n".join(lines)