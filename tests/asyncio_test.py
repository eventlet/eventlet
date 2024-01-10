"""Tests for asyncio integration."""

import asyncio

import pytest

from eventlet.hubs import get_hub
from eventlet.hubs.asyncio import Hub as AsyncioHub
from eventlet.asyncio import spawn_for_coroutine

from .wsgi_test import _TestBase, Site

if not isinstance(get_hub(), AsyncioHub):
    pytest.skip("Only works on asyncio hub", allow_module_level=True)


class CallingAsyncFunctionsFromGreenletsHighLevelTests(_TestBase):
    """
    High-level tests for using ``asyncio``-based code inside greenlets.

    For this functionality to be useful, users need to be able to use 3rd party
    libraries that use sockets etc..  Merely hooking up futures to greenlets
    doesn't help if you can't use the asyncio library ecosystem.  So this set
    of tests does more integration-y tests showing that functionality works.
    """

    def set_site(self):
        self.site = Site()

    def test_aiohttp_client(self):
        """
        The ``aiohttp`` HTTP client works correctly on top of eventlet.
        """
        import aiohttp

        async def request():
            host, port = self.server_addr
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://{host}:{port}/") as response:
                    html = await response.text()
                    return html

        gthread = spawn_for_coroutine(request())
        assert gthread.wait() == "hello world"


def test_result():
    """
    The result of the coroutine is returned by the ``GreenThread`` created by
    ``spawn_for_coroutine``.
    """

    async def go():
        await asyncio.sleep(0.0001)
        return 13

    assert spawn_for_coroutine(go()).wait() == 13


def test_exception():
    """
    An exception raised by the coroutine is raised by ``GreenThread.wait()``
    for the green thread created by ``spawn_for_coroutine()``.
    """

    async def go():
        await asyncio.sleep(0.0001)
        raise ZeroDivisionError()

    with pytest.raises(ZeroDivisionError):
        assert spawn_for_coroutine(go()).wait()
