import pytest

from app.services.hunt_policy import HuntPublicationPolicy


def test_hunt_publication_policy_default():
    policy = HuntPublicationPolicy()

    assert policy.max_publications_per_run == 3


def test_hunt_publication_policy_accepts_custom_limit():
    policy = HuntPublicationPolicy(
        max_publications_per_run=5
    )

    assert policy.max_publications_per_run == 5


def test_hunt_publication_policy_rejects_invalid_limit():
    with pytest.raises(ValueError):
        HuntPublicationPolicy(
            max_publications_per_run=0
        )
