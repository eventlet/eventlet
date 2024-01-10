"""Tests for asyncio integration."""

import pytest

from eventlet.hubs import get_hub
from eventlet.hubs.asyncio import Hub as AsyncioHub
from eventlet.asyncio import spawn_for_coroutine

from .wsgi_test import _TestBase, Site

IS_ASYNCIO = isinstance(get_hub(), AsyncioHub)

@pytest.mark.skipif(not IS_ASYNCIO, reason="Only works on asyncio hub")
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
