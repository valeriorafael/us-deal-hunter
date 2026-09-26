from datetime import datetime, timedelta

from app.models.price_history import PriceHistory


class PriceHistoryService:
    def __init__(
        self,
        history: list[PriceHistory],
        product_id: str | None = None,
    ):
        self.history = history
        self.product_id = product_id

    def _filter_by_days(
        self,
        days: int,
        now: datetime,
    ) -> list[PriceHistory]:
        cutoff = now - timedelta(days=days)

        return [
            item
            for item in self.history
            if item.recorded_at is not None
            and cutoff <= item.recorded_at <= now
            and (
                self.product_id is None
                or item.product_id == self.product_id
            )
        ]

    def average_price(
        self,
        days: int = 30,
        now: datetime | None = None,
    ) -> float | None:
        if now is None:
            now = datetime.now()

        prices = self._filter_by_days(days, now)

        if not prices:
            return None

        return sum(item.price for item in prices) / len(prices)

    def lowest_price(
        self,
        days: int = 90,
        now: datetime | None = None,
    ) -> float | None:
        if now is None:
            now = datetime.now()

        prices = self._filter_by_days(days, now)

        if not prices:
            return None

        return min(item.price for item in prices)

    def history_days(
        self,
        now: datetime | None = None,
    ) -> int:
        if now is None:
            now = datetime.now()

        timestamps = [
            item.recorded_at
            for item in self.history
            if item.recorded_at is not None
            and item.recorded_at <= now
            and (
                self.product_id is None
                or item.product_id == self.product_id
            )
        ]

        if not timestamps:
            return 0

        oldest = min(timestamps)

        return (now - oldest).days
