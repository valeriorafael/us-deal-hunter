import json
import os
from dataclasses import dataclass
from datetime import datetime

from dotenv import load_dotenv

from app.models.deal import Deal
from app.models.product import Product
from app.services.image_resolver import ImageResolver


@dataclass(frozen=True)
class CuratedDealConfig:
    deals: tuple[Deal, ...]
    max_publications_per_run: int = 3


class CuratedDealLoader:
    def __init__(
        self,
        image_resolver: ImageResolver | None = None,
    ):
        self.image_resolver = (
            image_resolver or ImageResolver()
        )

    def load(
        self,
        path: str = "data/curated_deals.json",
    ) -> CuratedDealConfig:
        load_dotenv()

        partner_tag = os.getenv(
            "AMAZON_PARTNER_TAG"
        )

        if not partner_tag:
            raise ValueError(
                "AMAZON_PARTNER_TAG is required for curated deals."
            )

        with open(
            path,
            "r",
            encoding="utf-8-sig",
        ) as file:
            data = json.load(file)

        now = datetime.now().astimezone()
        deals = []

        for item in data.get("deals", []):
            expires_at = item.get("expires_at")

            if expires_at:
                expiration = datetime.fromisoformat(
                    expires_at
                )

                if expiration <= now:
                    continue

            asin = item["asin"]

            product_url = (
                f"https://www.amazon.com/dp/{asin}"
            )

            affiliate_url = (
                f"{product_url}?tag={partner_tag}"
            )

            source_url = item.get(
                "source_url",
                "",
            )

            image_url = (
                item.get("image_url")
                or self.image_resolver.resolve(
                    source_url,
                    fallback_urls=[
                        product_url,
                    ],
                )
            )

            product = Product(
                product_id=asin,
                title=item["title"],
                current_price=float(
                    item["current_price"]
                ),
                currency="USD",
                rating=(
                    float(item["rating"])
                    if item.get("rating") is not None
                    else None
                ),
                review_count=int(
                    item.get("review_count", 0)
                ),
                platform="amazon",
                product_url=product_url,
                affiliate_url=affiliate_url,
                image_url=image_url,
            )

            deal = Deal(
                product=product,
                score=0.0,
                label="CURATED",
                confidence="VERIFIED",
                source_query=(
                    f"curated:{item['source_name']}"
                ),
                reference_price=float(
                    item["reference_price"]
                ),
                source_name=item["source_name"],
                source_url=source_url,
            )

            deals.append(deal)

        max_publications = int(
            data.get(
                "max_publications_per_run",
                3,
            )
        )

        if max_publications < 1:
            raise ValueError(
                "max_publications_per_run must be at least 1."
            )

        return CuratedDealConfig(
            deals=tuple(deals),
            max_publications_per_run=max_publications,
        )