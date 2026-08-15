from dataclasses import dataclass

from app.models.product import Product


@dataclass
class DealScore:
    """Result produced by the deal scoring engine."""

    score: float
    is_deal: bool

    price_score: float
    history_score: float
    rating_score: float
    review_score: float
    confidence_score: float


class DealScorer:
    """Calculate how attractive a product deal is."""

    DEAL_THRESHOLD = 85

    def score(self, product: Product) -> DealScore:
        price_score = self._price_score(product)
        history_score = self._history_score(product)
        rating_score = self._rating_score(product)
        review_score = self._review_score(product)
        confidence_score = self._confidence_score(product)

        total = (
            price_score
            + history_score
            + rating_score
            + review_score
            + confidence_score
        )

        total = max(0.0, min(100.0, total))

        return DealScore(
            score=round(total, 2),
            is_deal=total >= self.DEAL_THRESHOLD,
            price_score=round(price_score, 2),
            history_score=round(history_score, 2),
            rating_score=round(rating_score, 2),
            review_score=round(review_score, 2),
            confidence_score=round(confidence_score, 2),
        )

    def _price_score(self, product: Product) -> float:
        """Score based on discount against the 30-day average.

        Maximum: 40 points.
        """

        discount = product.discount_vs_30d

        if discount is None or discount <= 0:
            return 0.0

        if discount >= 0.25:
            return 40.0

        if discount >= 0.20:
            return 36.0

        if discount >= 0.15:
            return 32.0

        if discount >= 0.10:
            return 25.0

        if discount >= 0.05:
            return 15.0

        return 0.0

    def _history_score(self, product: Product) -> float:
        """Score based on proximity to the 90-day lowest price.

        Maximum: 20 points.
        """

        distance = product.distance_from_90d_low

        if distance is None:
            return 0.0

        if distance <= 0.03:
            return 20.0

        if distance <= 0.07:
            return 17.0

        if distance <= 0.10:
            return 14.0

        if distance <= 0.15:
            return 9.0

        if distance <= 0.20:
            return 4.0

        return 0.0

    def _rating_score(self, product: Product) -> float:
        """Score based on product rating.

        Maximum: 15 points.
        """

        if product.rating is None:
            return 0.0

        rating = max(0.0, min(5.0, product.rating))

        return (rating / 5.0) * 15.0

    def _review_score(self, product: Product) -> float:
        """Score based on review volume.

        Maximum: 10 points.
        """

        reviews = max(0, product.review_count)

        if reviews >= 10000:
            return 10.0

        if reviews >= 5000:
            return 8.0

        if reviews >= 1000:
            return 6.0

        if reviews >= 500:
            return 4.0

        if reviews >= 100:
            return 2.0

        return 0.0

    def _confidence_score(self, product: Product) -> float:
        """Score based on available historical price data.

        Maximum: 15 points.
        """

        has_average = product.average_price_30d is not None
        has_low = product.lowest_price_90d is not None

        if has_average and has_low:
            return 15.0

        if has_average or has_low:
            return 7.5

        return 0.0
