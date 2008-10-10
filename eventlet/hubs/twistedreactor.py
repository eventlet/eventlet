import threading
from eventlet import greenlib
from eventlet.support.greenlet import greenlet

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


class Hub:
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
        self.greenlet = None

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

        # if twisted's signal handlers are installed and mainLoop has just exited,
        # we must report the error to the user's greenlet.
        # QQQ actually we must raise this error in all the user's greenlets, to let them
        # clean up properly. never executing them again is cruel (unless they're daemons)
        raise AssertionError("reactor was stopped")

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

    def stop(self):
        from twisted.internet import reactor
        reactor.stop()

    def sleep(self, seconds=0):
        from twisted.internet import reactor
        d = reactor.callLater(seconds, greenlib.switch, greenlet.getcurrent())
        self.switch()

    def add_descriptor(self, fileno, read=None, write=None, exc=None):
        #print 'add_descriptor', fileno, read, write, exc
        descriptor = socket_rwdescriptor(fileno, read, write, exc)
        from twisted.internet import reactor
        if read:
            reactor.addReader(descriptor)
        if write:
            reactor.addWriter(descriptor)
        # XXX exc will not work if no read nor write
        return descriptor

    def remove_descriptor(self, descriptor):
        from twisted.internet import reactor
        reactor.removeReader(descriptor)
        reactor.removeWriter(descriptor)

    # required by GreenSocket
    def exc_descriptor(self, _fileno):
        pass # XXX do something sensible here

    # required by greenlet_body
    def cancel_timers(self, greenlet, quiet=False):
        pass # XXX do something sensible here

    def schedule_call(self, seconds, func, *args, **kwargs):
        from twisted.internet import reactor
        return reactor.callLater(seconds, func, *args, **kwargs)


class DaemonicThread(threading.Thread):
    def _set_daemon(self):
        return True

def make_twisted_threadpool_daemonic():
    from twisted.python.threadpool import ThreadPool
    if ThreadPool.threadFactory != DaemonicThread:
        ThreadPool.threadFactory = DaemonicThread

make_twisted_threadpool_daemonic() # otherwise the program would hang after the main greenlet exited
