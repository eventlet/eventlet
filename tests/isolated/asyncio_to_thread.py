import eventlet
from eventlet.patcher import original
from eventlet.asyncio import spawn_for_awaitable

eventlet.monkey_patch()
import asyncio


def in_thread():
    time = original("time")
    time.sleep(0.001)
    return 3 + 4


async def go():
    return await asyncio.gather(
        asyncio.to_thread(in_thread),
        asyncio.to_thread(in_thread),
        asyncio.to_thread(in_thread),
    )


if __name__ == "__main__":
    assert spawn_for_awaitable(go()).wait() == [7, 7, 7]
    print("pass")
