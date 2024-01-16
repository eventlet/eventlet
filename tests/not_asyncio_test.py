"""Tests for hubs that are not asyncio-based."""

import pytest

from eventlet.hubs import get_hub
from eventlet.hubs.asyncio import Hub as AsyncioHub
from eventlet.asyncio import spawn_for_awaitable

if isinstance(get_hub(), AsyncioHub):
    pytest.skip("Only works on non-asyncio hub", allow_module_level=True)


def test_spawn_from_coroutine_errors():
    """
    If ``spawn_for_awaitable()`` is called in a non-asyncio hub it will raise a
    ``RuntimeError``.
    """

    async def go():
        return 13

    with pytest.raises(RuntimeError):
        spawn_for_awaitable(go())
