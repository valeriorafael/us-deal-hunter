import pytest

from app.platforms.base import PlatformAdapter


def test_platform_adapter_is_abstract():
    with pytest.raises(TypeError):
        PlatformAdapter()
