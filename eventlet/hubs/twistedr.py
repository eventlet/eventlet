import sys
import threading
import weakref
from twisted.internet.base import DelayedCall as TwistedDelayedCall
from eventlet.hubs.hub import _g_debug
from eventlet import greenlib
from eventlet.support.greenlet import greenlet

import traceback


class DelayedCall(TwistedDelayedCall):
    "fix DelayedCall to behave like eventlet's Timer in some respects"

    def cancel(self):
        if self.cancelled or self.called:
            self.cancelled = True
            return
        return TwistedDelayedCall.cancel(self)

def callLater(reactor, _seconds, _f, *args, **kw):
    # the same as original but creates fixed DelayedCall instance 
    assert callable(_f), "%s is not callable" % _f
    assert sys.maxint >= _seconds >= 0, \
           "%s is not greater than or equal to 0 seconds" % (_seconds,)
    tple = DelayedCall(reactor.seconds() + _seconds, _f, args, kw,
                       reactor._cancelCallLater,
                       reactor._moveCallLaterSooner,
                       seconds=reactor.seconds)
    reactor._newTimedCalls.append(tple)
    return tple

class socket_rwdescriptor:
    #implements(IReadWriteDescriptor)

    def __init__(self, fileno, read, write, error):
        self._fileno = fileno
        self.read = read
        self.write = write
        self.error = error

    def doRead(self):
        if self.read:
            self.read(self)

    def doWrite(self):
        if self.write:
            self.write(self)

    def connectionLost(self, reason):
        if self.error:
            self.error(self, reason)

    def fileno(self):
        return self._fileno

    logstr = "XXXfixme"

    def logPrefix(self):
        return self.logstr


class BaseTwistedHub(object):
    """This hub does not run a dedicated greenlet for the mainloop (unlike TwistedHub).
    Instead, it assumes that the mainloop is run in the main greenlet.
    
    This makes running "green" functions in the main greenlet impossible but is useful
    when you want to call reactor.run() yourself.
    """
    def __init__(self, mainloop_greenlet):
        self.greenlet = mainloop_greenlet
        self.waiters_by_greenlet = {}
        self.timers_by_greenlet = {}

    def switch(self):
        assert greenlet.getcurrent() is not self.greenlet, 'Impossible to switch() from the mainloop greenlet'
        try:
           greenlet.getcurrent().parent = self.greenlet
        except ValueError, ex:
           pass
        return greenlib.switch(self.greenlet)

    def stop(self):
        from twisted.internet import reactor
        reactor.stop()

    def add_descriptor(self, fileno, read=None, write=None, exc=None):
        from twisted.internet import reactor
        descriptor = socket_rwdescriptor(fileno, read, write, exc)
        if read:
            reactor.addReader(descriptor)
        if write:
            reactor.addWriter(descriptor)
        # XXX exc will not work if no read nor write
        self.waiters_by_greenlet[greenlet.getcurrent()] = descriptor
        return descriptor

    def remove_descriptor(self, descriptor):
        from twisted.internet import reactor
        reactor.removeReader(descriptor)
        reactor.removeWriter(descriptor)
        self.waiters_by_greenlet.pop(greenlet.getcurrent(), None)

    def exc_greenlet(self, gr, exception_object):
        fileno = self.waiters_by_greenlet.pop(gr, None)
        if fileno is not None:
            self.remove_descriptor(fileno)
        greenlib.switch(gr, None, exception_object)

    # required by GreenSocket
    def exc_descriptor(self, _fileno):
        pass # XXX do something sensible here

    def schedule_call(self, seconds, func, *args, **kwargs):
        from twisted.internet import reactor
        def call_with_timer_attached(*args1, **kwargs1):
            try:
                return func(*args1, **kwargs1)
            finally:
                if seconds:
                    self.timer_finished(timer)
        timer = callLater(reactor, seconds, call_with_timer_attached, *args, **kwargs)
        if seconds:
            self.track_timer(timer)
        return timer

    def track_timer(self, timer):
        try:
            current_greenlet = greenlet.getcurrent()
            timer.greenlet = current_greenlet
            self.timers_by_greenlet.setdefault(
                current_greenlet,
                weakref.WeakKeyDictionary())[timer] = True
        except:
            print 'track_timer failed'
            traceback.print_exc()
            raise

    def timer_finished(self, timer):
        try:
            greenlet = timer.greenlet
            del self.timers_by_greenlet[greenlet][timer]
            if not self.timers_by_greenlet[greenlet]:
                del self.timers_by_greenlet[greenlet]
        except (AttributeError, KeyError):
            pass
        except:
            print 'timer_finished failed'
            traceback.print_exc()
            raise

    def cancel_timers(self, greenlet, quiet=False):
        try:
            if greenlet not in self.timers_by_greenlet:
                return
            for timer in self.timers_by_greenlet[greenlet].keys():
                if not timer.cancelled and not timer.called and hasattr(timer, 'greenlet'):
                    ## If timer.seconds is 0, this isn't a timer, it's
                    ## actually eventlet's silly way of specifying whether
                    ## a coroutine is "ready to run" or not.
                    ## TwistedHub: I do the same, by not attaching 'greenlet' attribute to zero-timers QQQ
                    try:
                        # this might be None due to weirdness with weakrefs
                        timer.cancel()
                    except TypeError:
                        pass
                    if _g_debug and not quiet:
                        print 'Hub cancelling left-over timer %s' % timer
            try:
                del self.timers_by_greenlet[greenlet]
            except KeyError:
                pass
        except:
            print 'cancel_timers failed'
            import traceback
            traceback.print_exc()
            if not quiet:
                raise

    def abort(self):
        from twisted.internet import reactor
        reactor.crash()

    @property
    def running(self):
        from twisted.internet import reactor
        return reactor.running

    # for debugging:

    def get_readers(self):
        from twisted.internet import reactor
        readers = reactor.getReaders()
        readers.remove(getattr(reactor, 'waker'))
        return readers

    def get_writers(self):
        from twisted.internet import reactor
        return reactor.getWriters()

    def get_excs(self):
        return []

    def get_timers_count(self):
        from twisted.internet import reactor
        return len(reactor.getDelayedCalls())



class TwistedHub(BaseTwistedHub):
    # wrapper around reactor that runs reactor's main loop in a separate greenlet.
    # whenever you need to wait, i.e. inside a call that must appear
    # blocking, call hub.switch() (then your blocking operation should switch back to you
    # upon completion)

    # unlike other eventlet hubs, which are created per-thread,
    # this one cannot be instantiated more than once, because
    # twisted doesn't allow that

    # 0-not created
    # 1-initialized but not started
    # 2-started
    # 3-restarted
    state = 0

    installSignalHandlers = False

    def __init__(self):
        assert Hub.state==0, ('This hub can only be instantiated once', Hub.state)
        Hub.state = 1
        make_twisted_threadpool_daemonic() # otherwise the program would hang after the main greenlet exited
        BaseTwistedHub.__init__(self, None)

    def switch(self):
        if not self.greenlet:
            self.greenlet = greenlib.tracked_greenlet()
            args = ((self.run,),)
        else:
            args = ()
        try:
           greenlet.getcurrent().parent = self.greenlet
        except ValueError, ex:
           pass
        return greenlib.switch(self.greenlet, *args)

    def run(self, installSignalHandlers=None):
        if installSignalHandlers is None:
            installSignalHandlers = self.installSignalHandlers
        
        # main loop, executed in a dedicated greenlet
        from twisted.internet import reactor
        assert Hub.state in [1, 3], ('run function is not reentrant', Hub.state)

        if Hub.state == 1:
            reactor.startRunning(installSignalHandlers=installSignalHandlers)
        elif not reactor.running:
            # if we're here, then reactor was explicitly stopped with reactor.stop()
            # restarting reactor (like we would do after an exception) in this case
            # is not an option.
            raise AssertionError("reactor is not running")

        try:
            self.mainLoop(reactor)
        except:
            # an exception in the mainLoop is a normal operation (e.g. user's
            # signal handler could raise an exception). In this case we will re-enter
            # the main loop at the next switch.
            Hub.state = 3
            raise
        
        # clean exit here is needed for abort() method to work
        # do not raise an exception here.

    def mainLoop(self, reactor):
        Hub.state = 2
        # Unlike reactor's mainLoop, this function does not catch exceptions.
        # Anything raised goes into the main greenlet (because it is always the
        # parent of this one)
        while reactor.running:
            # Advance simulation time in delayed event processors.
            reactor.runUntilCurrent()
            t2 = reactor.timeout()
            t = reactor.running and t2
            reactor.doIteration(t)

Hub = TwistedHub

class DaemonicThread(threading.Thread):
    def _set_daemon(self):
        return True

def make_twisted_threadpool_daemonic():
    from twisted.python.threadpool import ThreadPool
    if ThreadPool.threadFactory != DaemonicThread:
        ThreadPool.threadFactory = DaemonicThread


