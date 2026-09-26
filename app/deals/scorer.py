from app.models.deal import Deal
from app.models.product import Product


class DealScorer:
    """
    Evaluates how attractive a product deal is.

    Score:
        0-39   = WEAK
        40-59  = FAIR
        60-79  = GOOD
        80-100 = GREAT

    Confidence:
        LOW    = little or no historical price data
        MEDIUM = partial or short historical data
        HIGH   = sufficiently complete historical data
    """

    def evaluate(self, product: Product) -> Deal:
        score = 0.0
        reasons = []

        # ---------------------------------------------------------
        # 1. Historical discount: up to 60 points
        # ---------------------------------------------------------
        discount = product.discount_vs_30d

        if discount is not None and discount > 0:
            discount_points = min(discount * 350, 60)
            score += discount_points

            if discount >= 0.10:
                reasons.append(
                    f"{discount:.1%} below 30-day average"
                )

        # ---------------------------------------------------------
        # 2. Distance from 90-day low: up to 25 points
        # ---------------------------------------------------------
        distance = product.distance_from_90d_low

        if distance is not None and distance >= 0:
            if distance <= 0.05:
                score += 25
                reasons.append("Near the 90-day low")
            elif distance <= 0.10:
                score += 15
                reasons.append("Close to the 90-day low")
            elif distance <= 0.20:
                score += 5

        # ---------------------------------------------------------
        # 3. Product quality: up to 15 points
        # ---------------------------------------------------------
        rating = product.rating
        reviews = product.review_count

        if rating is not None:
            if rating >= 4.5:
                score += 10
                reasons.append("Excellent rating")
            elif rating >= 4.0:
                score += 7
            elif rating >= 3.5:
                score += 3

        if reviews >= 1000:
            score += 5
            reasons.append("Strong review volume")
        elif reviews >= 100:
            score += 3
        elif reviews >= 20:
            score += 1

        # ---------------------------------------------------------
        # 4. Confidence based on historical price data
        # ---------------------------------------------------------
        has_30d_history = product.average_price_30d is not None
        has_90d_history = product.lowest_price_90d is not None
        history_days = product.price_history_days

        if not has_30d_history and not has_90d_history:
            confidence = "LOW"

        elif history_days is None:
            # Backward compatibility:
            # historical fields exist, but duration is unknown.
            if has_30d_history and has_90d_history:
                confidence = "HIGH"
            else:
                confidence = "MEDIUM"

        elif history_days < 7:
            confidence = "LOW"

        elif history_days < 30:
            confidence = "MEDIUM"

        elif has_30d_history and has_90d_history:
            confidence = "HIGH"

        else:
            confidence = "MEDIUM"

        # ---------------------------------------------------------
        # Clamp score to 0-100
        # ---------------------------------------------------------
        score = min(max(score, 0.0), 100.0)

        # ---------------------------------------------------------
        # Classification
        # ---------------------------------------------------------
        if score >= 80:
            label = "GREAT"
        elif score >= 60:
            label = "GOOD"
        elif score >= 40:
            label = "FAIR"
        else:
            label = "WEAK"

        return Deal(
            product=product,
            score=score,
            label=label,
            reasons=tuple(reasons),
            confidence=confidence,
        )
