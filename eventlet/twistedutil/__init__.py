from twisted.internet import defer
from twisted.python import failure
from eventlet.support.greenlet import greenlet
from eventlet import greenlib
from eventlet.api import get_hub, spawn

def block_on(deferred):
    cur = [greenlet.getcurrent()]
    def cb(value):
        if cur:
            greenlib.switch(cur[0], value)
        return value
    def eb(err):
        if cur:
            greenlib.switch(cur[0], exc=(err.type, err.value, err.tb))
        return err
    deferred.addCallback(cb)
    deferred.addErrback(eb)
    try:
        return get_hub().switch()
    finally:
        del cur[0]

def _putResultInDeferred(deferred, f, args, kwargs):
    try:
        result = f(*args, **kwargs)
    except:
        f = failure.Failure()
        deferred.errback(f)
    else:
        deferred.callback(result)

def deferToGreenThread(func, *args, **kwargs):
    d = defer.Deferred()
    spawn(_putResultInDeferred, d, func, args, kwargs)
    return d

def callInGreenThread(func, *args, **kwargs):
    return spawn(func, *args, **kwargs)

