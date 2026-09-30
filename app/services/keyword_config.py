import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KeywordConfig:
    query: str
    search_index: str = "All"
    item_count: int = 10
    item_page: int = 1
    min_saving_percent: float | None = None


@dataclass(frozen=True)
class KeywordFileConfig:
    keywords: tuple[KeywordConfig, ...]
    max_publications_per_run: int = 3


class KeywordConfigLoader:
    @staticmethod
    def load_config(
        path: str = "data/keywords.json",
    ) -> KeywordFileConfig:
        file_path = Path(path)

        if not file_path.exists():
            raise ValueError(
                f"Keyword file not found: {path}"
            )

        try:
            data = json.loads(
                file_path.read_text(
                    encoding="utf-8-sig"
                )
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid keyword JSON: {exc}"
            ) from exc

        items = data.get("keywords")

        if not isinstance(items, list) or not items:
            raise ValueError(
                "Keyword file must contain a non-empty 'keywords' list."
            )

        max_publications = data.get(
            "max_publications_per_run",
            3,
        )

        try:
            max_publications = int(max_publications)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "max_publications_per_run must be an integer."
            ) from exc

        if max_publications < 1:
            raise ValueError(
                "max_publications_per_run must be at least 1."
            )

        configs = []

        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Keyword entry {index} must be an object."
                )

            query = str(item.get("query", "")).strip()

            if not query:
                raise ValueError(
                    f"Keyword entry {index} has no query."
                )

            configs.append(
                KeywordConfig(
                    query=query,
                    search_index=str(
                        item.get("search_index", "All")
                    ),
                    item_count=int(
                        item.get("item_count", 10)
                    ),
                    item_page=int(
                        item.get("item_page", 1)
                    ),
                    min_saving_percent=(
                        float(item["min_saving_percent"])
                        if item.get("min_saving_percent") is not None
                        else None
                    ),
                )
            )

        return KeywordFileConfig(
            keywords=tuple(configs),
            max_publications_per_run=max_publications,
        )

    @staticmethod
    def load(
        path: str = "data/keywords.json",
    ) -> list[KeywordConfig]:
        return list(
            KeywordConfigLoader.load_config(path).keywords
        )
