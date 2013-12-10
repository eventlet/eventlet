import os


_child_callbacks = []


def register_child_callback(callback):
    _child_callbacks.append(callback)


__original_fork__ = os.fork
def _patched_fork():
    pid = __original_fork__()
    if pid == 0:
        for callback in _child_callbacks:
            callback()
    return pid
os.fork = _patched_fork
