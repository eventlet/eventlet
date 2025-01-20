"""Tests for asyncio integration."""

import pytest

import eventlet
from eventlet.hubs import get_hub
from eventlet.hubs.asyncio import Hub as AsyncioHub
if not isinstance(get_hub(), AsyncioHub):
    pytest.skip("Only works on asyncio hub", allow_module_level=True)

import asyncio
from time import time
import socket
import sys

from greenlet import GreenletExit

from eventlet.asyncio import spawn_for_awaitable
from eventlet.greenthread import getcurrent
from eventlet.support import greendns
from .wsgi_test import _TestBase, Site

import tests


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
        return 1 / 0

    async def go():
        try:
            await eventlet.spawn(greenlet)
        except ZeroDivisionError as e:
            return e

    result = spawn_for_awaitable(go()).wait()
    assert isinstance(result, ZeroDivisionError)


def test_await_greenthread_success_immediate():
    """
    ``await`` on a ``GreenThread`` returns its immediate result.
    """

    def greenlet():
        return 23

    async def go():
        result = await eventlet.spawn(greenlet)
        return result

    assert spawn_for_awaitable(go()).wait() == 23


def test_await_greenthread_exception_immediate():
    """
    ``await`` on a ``GreenThread`` raises its immediate exception.
    """

    def greenlet():
        return 1 / 0

    async def go():
        try:
            await eventlet.spawn(greenlet)
        except ZeroDivisionError as e:
            return e

    result = spawn_for_awaitable(go()).wait()
    assert isinstance(result, ZeroDivisionError)


def test_ensure_future():
    """
    ``asyncio.ensure_future()`` works correctly on a ``GreenThread``.
    """

    def greenlet():
        eventlet.sleep(0.001)
        return 27

    async def go():
        future = asyncio.ensure_future(eventlet.spawn(greenlet))
        result = await future
        return result

    assert spawn_for_awaitable(go()).wait() == 27


def test_cancelling_future_kills_greenthread():
    """
    If the ``Future`` created by ``asyncio.ensure_future(a_green_thread)`` is
    cancelled, the ``a_green_thread`` ``GreenThread`` is killed.
    """

    phases = []

    def green():
        phases.append(1)
        future.cancel()
        eventlet.sleep(1)
        # This should never be reached:
        phases.append(2)

    gthread = eventlet.spawn(green)

    async def go():
        try:
            await gthread
        except asyncio.CancelledError:
            return "good"
        else:
            return "bad"

    future = asyncio.ensure_future(go())
    assert spawn_for_awaitable(future).wait() == "good"

    with pytest.raises(GreenletExit):
        gthread.wait()
    assert phases == [1]


def test_greenthread_killed_while_awaited():
    """
    If a ``GreenThread`` is killed, the ``async`` function ``await``ing it sees
    it as cancellation.
    """
    phases = []

    def green():
        phases.append(1)
        eventlet.sleep(0.001)
        phases.append(2)
        getcurrent().kill()
        eventlet.sleep(1)
        # Should never be reached:
        phases.append(3)

    gthread = eventlet.spawn(green)

    async def go():
        try:
            await gthread
            return "where is my cancellation?"
        except asyncio.CancelledError:
            return "canceled!"

    assert spawn_for_awaitable(go()).wait() == "canceled!"
    assert phases == [1, 2]


@pytest.mark.skipif(
    sys.version_info[:2] < (3, 9), reason="to_thread() is new Python 3.9"
)
def test_asyncio_to_thread():
    """
    ``asyncio.to_thread()`` works with Eventlet.
    """
    tests.run_isolated("asyncio_to_thread.py")


def test_asyncio_does_not_use_greendns():
    """
    ``asyncio`` loops' ``getaddrinfo()`` and ``getnameinfo()`` do not use green
    DNS.
    """
    tests.run_isolated("asyncio_dns.py")


def test_make_sure_monkey_patching_asyncio_is_restricted():
    """
    ``asyncio`` continues to have original, unpatched ``socket`` etc classes.
    """
    tests.run_isolated("asyncio_correct_patching.py")
