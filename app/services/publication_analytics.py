from datetime import datetime, timedelta

from app.services.publication_repository import (
    PublicationRepository,
)


class PublicationAnalytics:
    def __init__(
        self,
        repository: PublicationRepository | None = None,
    ):
        self.repository = (
            repository or PublicationRepository()
        )

    def total_published(self) -> int:
        return self.repository.total()

    def published_last_24h(
        self,
        now: datetime | None = None,
    ) -> int:
        now = now or datetime.now()

        return self.repository.count_since(
            now - timedelta(hours=24)
        )

    def average_score(self) -> float | None:
        return self.repository.average_score()

    def top_queries(
        self,
        limit: int = 10,
    ) -> list[tuple[str, int]]:
        return self.repository.top_queries(
            limit=limit
        )