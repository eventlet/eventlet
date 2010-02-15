version_info = (0, 9, 4)
__version__ = '%s.%s.%s' % version_info

try:
    from eventlet import greenthread
    from eventlet import greenpool
    from eventlet import queue
    from eventlet import timeout

    sleep = greenthread.sleep
    spawn = greenthread.spawn
    spawn_n = greenthread.spawn_n
    spawn_after = greenthread.spawn_after
    
    Timeout = timeout.Timeout
    with_timeout = timeout.with_timeout
    
    GreenPool = greenpool.GreenPool
    GreenPile = greenpool.GreenPile
    
    Queue = queue.Queue
    
    # deprecated    
    TimeoutError = timeout.Timeout
    exc_after = greenthread.exc_after
    call_after_global = greenthread.call_after_global
except ImportError:
    # this is to make Debian packaging easier
    import traceback
    traceback.print_exc()