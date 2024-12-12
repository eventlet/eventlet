"""
asyncio submodules continue to have the original, real socket module even after
monkeypatching.
"""

import sys


def assert_correct_patching():
    from eventlet.greenio.base import GreenSocket
    import asyncio.selector_events
    if asyncio.selector_events.socket.socket is GreenSocket:
        raise RuntimeError("Wrong socket class, should've been normal socket.socket")

    import asyncio.selector_events
    if asyncio.selector_events.selectors is not sys.modules["__original_module_selectors"]:
        raise RuntimeError("Wrong selectors")

    if asyncio.selector_events.selectors.select is not sys.modules["__original_module_select"]:
        raise RuntimeError("Wrong select")


import eventlet.hubs
eventlet.hubs.get_hub()
assert_correct_patching()

import eventlet
eventlet.monkey_patch()
assert_correct_patching()


print("pass")
