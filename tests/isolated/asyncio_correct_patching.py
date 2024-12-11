"""
asyncio submodules continue to have the original, real socket module even after
monkeypatching.
"""
import eventlet
eventlet.monkey_patch()
import eventlet.hubs
eventlet.hubs.get_hub()

from eventlet.greenio.base import GreenSocket
import asyncio.selector_events
if asyncio.selector_events.socket.socket is GreenSocket:
    raise RuntimeError("Wrong socket class, should've been normal socket.socket")
print("pass")
