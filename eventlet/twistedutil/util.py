from twisted.internet import defer
from twisted.python import failure
from eventlet.support.greenlet import greenlet
from eventlet import greenlib
from eventlet.api import get_hub, spawn

def block_on(deferred):
    cur = greenlet.getcurrent()
    def cb(value):
        greenlib.switch(cur, value)
    def eb(err):
        greenlib.switch(cur, exc=(err.type, err.value, err.tb))
    deferred.addCallback(cb)
    deferred.addErrback(eb)
    return get_hub().switch()

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

