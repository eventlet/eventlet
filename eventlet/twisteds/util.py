from functools import wraps
from eventlet.support.greenlet import greenlet
from eventlet import greenlib
from eventlet.api import get_hub

def block_on(deferred):
    cur = greenlet.getcurrent()
    def cb(value):
        greenlib.switch(cur, value)
    def eb(err):
        greenlib.switch(cur, exc=(err.type, err.value, err.tb))
    deferred.addCallback(cb)
    deferred.addErrback(eb)
    return get_hub().switch()
