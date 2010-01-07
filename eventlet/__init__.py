version_info = (0, 9, '3pre')
__version__ = '%s.%s.%s' % version_info

from eventlet import greenthread
from eventlet import greenpool

sleep = greenthread.sleep

spawn = greenthread.spawn
spawn_n = greenthread.spawn_n
call_after_global = greenthread.call_after_global
call_after_local = greenthread.call_after_local
TimeoutError = greenthread.TimeoutError
exc_after = greenthread.exc_after
with_timeout = greenthread.with_timeout

GreenPool = greenpool.GreenPool
GreenPile = greenpool.GreenPile
