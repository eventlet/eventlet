import eventlet.patcher
if eventlet.patcher.is_monkey_patched("socket"):
    raise RuntimeError("Monkey patching should not have happened")
print("pass")
