"""Tests for asyncio integration."""

import asyncio
from time import time

import pytest

from greenlet import GreenletExit

import eventlet
from eventlet.hubs import get_hub
from eventlet.hubs.asyncio import Hub as AsyncioHub
from eventlet.asyncio import spawn_for_awaitable
from eventlet.greenthread import getcurrent
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
                url = "http://{}:{}/".format(host, port)
                async with session.get(url) as response:
                    html = await response.text()
                    return html

        gthread = spawn_for_awaitable(request())
        assert gthread.wait() == "hello world"


def test_result():
    """
    The result of the coroutine is returned by the ``GreenThread`` created by
    ``spawn_for_awaitable``.
    """

    async def go():
        await asyncio.sleep(0.0001)
        return 13

    assert spawn_for_awaitable(go()).wait() == 13


def test_exception():
    """
    An exception raised by the coroutine is raised by ``GreenThread.wait()``
    for the green thread created by ``spawn_for_awaitable()``.
    """

    async def go():
        await asyncio.sleep(0.0001)
        raise ZeroDivisionError()

    with pytest.raises(ZeroDivisionError):
        assert spawn_for_awaitable(go()).wait()


def test_future_and_task():
    """
    ``spawn_for_awaitable()`` can take an ``asyncio.Future`` or an
    ``asyncio.Task``.
    """

    async def go(value):
        return value * 2

    assert spawn_for_awaitable(asyncio.ensure_future(go(8))).wait() == 16
    assert spawn_for_awaitable(asyncio.create_task(go(6))).wait() == 12


def test_asyncio_sleep():
    """
    ``asyncio`` scheduled events work on eventlet.
    """

    async def go():
        start = time()
        await asyncio.sleep(0.07)
        return time() - start

    elapsed = spawn_for_awaitable(go()).wait()
    assert 0.05 < elapsed < 0.09


def test_kill_greenthread():
    """
    If a ``GreenThread`` wrapping an ``asyncio.Future``/coroutine is killed,
    the ``asyncio.Future`` is cancelled.
    """

    the_greenthread = []
    progress = []

    async def go():
        await asyncio.sleep(0.1)
        progress.append(1)
        while not the_greenthread:
            await asyncio.sleep(0.001)
        # Kill the green thread.
        progress.append(2)
        the_greenthread[0].kill()
        progress.append(3)
        await asyncio.sleep(1)
        # This should never be reached:
        progress.append(4)

    future = asyncio.ensure_future(go())
    the_greenthread.append(spawn_for_awaitable(future))
    with pytest.raises(GreenletExit):
        the_greenthread[0].wait()
    assert progress == [1, 2, 3]
    # Cancellation may not be immediate.
    eventlet.sleep(0.01)
    assert future.cancelled()
    assert progress == [1, 2, 3]


def test_await_greenthread_success():
    """
    ``await`` on a ``GreenThread`` returns its eventual result.
    """
    def greenlet():
        eventlet.sleep(0.001)
        return 23

    async def go():
        result = await eventlet.spawn(greenlet)
        return result

    assert spawn_for_awaitable(go()).wait() == 23


def test_await_greenthread_exception():
    """
    ``await`` on a ``GreenThread`` raises its eventual exception.
    """
    def greenlet():
        eventlet.sleep(0.001)
        1/0

    async def go():
        try:
            await eventlet.spawn(greenlet)
        except ZeroDivisionError as e:
            return e

    result = spawn_for_awaitable(go()).wait()
    assert isinstance(result, ZeroDivisionError)
