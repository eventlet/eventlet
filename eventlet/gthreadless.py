import greenlet
greenlet.main = greenlet.getcurrent() # WTF did greenlet.main go?
from twisted.internet import defer, reactor

def _desc(g):
    if isinstance(g, DebugGreenlet):
        if hasattr(g, 'name'):
            desc = "<%s %s" % (g.name, hex(id(g)))
        else:
            desc = "<NO NAME!? %s" % (hex(id(g)), )
    else:
        desc = "<%s" % (hex(id(g)),)
    if g is greenlet.main:
        desc += " (main)"
    desc += ">"
    return desc


class DebugGreenlet(greenlet.greenlet):
    __slots__ = ('name',)
    def __init__(self, func, name=None):
        super(DebugGreenlet, self).__init__(func)
        self.name = name
    def switch(self, *args, **kwargs):
        current = greenlet.getcurrent()
        #print "%s -> %s" % (_desc(current), _desc(self))
        return super(DebugGreenlet, self).switch(*args, **kwargs)

def deferredGreenlet(func):
    """
    I am a function decorator for functions that call blockOn.  The
    function I return will call the original function inside of a
    greenlet, and return a Deferred.

    TODO: Do a hack so the name of 'replacement' is the name of 'func'.
    """
    def replacement(*args, **kwargs):
        d = defer.Deferred()
        def greenfunc(*args, **kwargs):
            try:
                d.callback(func(*args, **kwargs))
            except:
                d.errback()
        g = greenlet.greenlet(greenfunc)
        crap = g.switch(*args, **kwargs)
        return d
    return replacement

class CalledFromMain(Exception):
    pass

class _IAmAnException(object):
    def __init__(self, f):
        self.f = f

def blockOn(d, desc=None):
    """
    Use me in non-main greenlets to wait for a Deferred to fire.
    """
    g = greenlet.getcurrent()
    if g is greenlet.main:
        raise CalledFromMain("You cannot call blockOn from the main greenlet.")

    ## Note ##
    # Notice that this code catches and ignores GreenletExit. The
    # greenlet mechanism sends a GreenletExit at a blocking greenlet if
    # there is no chance that the greenlet will be fired by anyone
    # else -- that is, no other greenlets have a reference to the one
    # that's blocking.

    # This is often the case with blockOn. When someone blocks on a
    # Deferred, these callbacks are added to it. When the deferred
    # fires, we make the blockOn() call finish -- we resume the
    # blocker.  At that point, the Deferred chain is irrelevant; it
    # makes no sense for any other callbacks to be called. The
    # Deferred, then, will likely be garbage collected and thus all
    # references to our greenlet will be lost -- and thus it will have
    # GreenletExit fired.

    def cb(r):
        try:
            # This callback might be fired immediately when added
            # and switching to the current greenlet seems to do nothing
            # (ie. we will never actually return to the function we called
            # blockOn from), so we make the call happen later in the main greenlet
            # instead, if the current greenlet is the same as the one we are swithcing
            # to.

            if g == greenlet.getcurrent():
                reactor.callLater(0, g.switch, r)
            else:    
                g.switch(r)
        except greenlet.GreenletExit:
            pass
    def eb(f):
        try:
            g.switch(_IAmAnException(f))
        except greenlet.GreenletExit:
            pass

    d.addCallbacks(cb, eb)

    x = g.parent.switch()
    if isinstance(x, _IAmAnException):
        x.f.raiseException()
    return x


class GreenletWrapper(object):
    """Wrap an object which presents an asynchronous interface (via Deferreds).
    
    The wrapped object will present the same interface, but all methods will
    return results, rather than Deferreds.
    
    When a Deferred would otherwise be returned, a greenlet is created and then
    control is switched back to the main greenlet.  When the Deferred fires,
    control is switched back to the created greenlet and execution resumes with
    the result.
    """

    def __init__(self, wrappee):  
        self.wrappee = wrappee

    def __getattribute__(self, name):
        wrappee = super(GreenletWrapper, self).__getattribute__('wrappee')
        original = getattr(wrappee, name)
        if callable(original):
            def wrapper(*a, **kw):
                result = original(*a, **kw)
                if isinstance(result, defer.Deferred):
                    return blockOn(result)
                return result
            return wrapper
        return original

