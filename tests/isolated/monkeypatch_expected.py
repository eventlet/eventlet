import eventlet.patcher
if not eventlet.patcher.is_monkey_patched("socket"):
    raise RuntimeError("Monkey patching should have happened")
print("pass")
