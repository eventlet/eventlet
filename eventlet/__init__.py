version_info = (0, 9, 4)
__version__ = '%s.%s.%s' % version_info

try:
    from eventlet import greenthread
    from eventlet import greenpool
    from eventlet import queue

    sleep = greenthread.sleep
    
    spawn = greenthread.spawn
    spawn_n = greenthread.spawn_n
    call_after_global = greenthread.call_after_global
    TimeoutError = greenthread.TimeoutError
    exc_after = greenthread.exc_after
    with_timeout = greenthread.with_timeout
    
    GreenPool = greenpool.GreenPool
    GreenPile = greenpool.GreenPile
    
    Queue = queue.Queue
except ImportError:
    # this is to make Debian packaging easier
    import traceback
    traceback.print_exc()