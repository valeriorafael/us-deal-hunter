from dataclasses import dataclass


@dataclass(frozen=True)
class HuntPublicationPolicy:
    """
    Controls how many successful publications a single hunt
    may produce.
    """

    max_publications_per_run: int = 3

    def __post_init__(self):
        if self.max_publications_per_run < 1:
            raise ValueError(
                "max_publications_per_run must be at least 1."
            )
