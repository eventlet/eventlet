import asyncio
import eventlet
try:
    eventlet.monkey_patch()
except RuntimeError as e:
    assert "asyncio has already been imported" in str(e)
else:
    raise RuntimeError("No error raised, this is a bug")

print("pass")
