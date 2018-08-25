__all__ = ('sleep', 'monotonic')

__time = __import__('time')
from eventlet import patcher
__patched__ = ['sleep']
patcher.slurp_properties(__time, globals(), ignore=__patched__, srckeys=dir(__time))
from eventlet.greenthread import sleep
sleep  # silence pyflakes

os = patcher.original('os')
mod = os.environ.get('EVENTLET_CLOCK')
if not mod:
    method = 'monotonic'
    monotonic = getattr(__time, method) if hasattr(__time, method) else getattr(patcher.original(method), method)
    del method
else:
    mod = mod.rsplit('.', 1)
    monotonic = getattr(patcher.original(mod[0]), mod[1])
del os
del mod
del patcher
