import eventlet
eventlet.monkey_patch()

import asyncio
import socket

from eventlet.asyncio import spawn_for_awaitable
from eventlet.support import greendns


def fail(*args, **kwargs):
    raise RuntimeError("This should not have been called")


greendns.resolve = fail
greendns.resolver.query = fail


async def lookups():
    loop = asyncio.get_running_loop()
    await loop.getaddrinfo("127.0.0.1", 80)
    await loop.getnameinfo(("127.0.0.1", 80), socket.NI_NUMERICHOST)
    return "ok"


if not spawn_for_awaitable(lookups()).wait() == "ok":
    raise RuntimeError("ono")

print("pass")
