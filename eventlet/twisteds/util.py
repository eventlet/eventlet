from twisted.internet import defer
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

def callInGreenThread(func, *args, **kwargs):
    result = defer.Deferred()
    def signal_deferred():
        try:
            value = func(*args, **kwargs)
        except Exception, ex:
            result.errback(ex)
        else:
            result.callback(value)
    spawn(signal_deferred)
    return result
