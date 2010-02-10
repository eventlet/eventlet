import bisect
import sys
import traceback
import time

from eventlet.support import greenlets as greenlet
from eventlet.timer import Timer, LocalTimer

READ="read"
WRITE="write"

class FdListener(object):
    def __init__(self, evtype, fileno, cb):
        assert (evtype is READ or evtype is WRITE)
        self.evtype = evtype
        self.fileno = fileno
        self.cb = cb
    def __call__(self, *args, **kw):
        return self.cb(*args, **kw)
    def __repr__(self):
        return "%s(%r, %r, %r)" % (type(self).__name__, self.evtype, self.fileno, self.cb)
    __str__ = __repr__
    
    
# in debug mode, track the call site that created the listener
class DebugListener(FdListener):
    def __init__(self, evtype, fileno, cb):
        self.where_called = traceback.format_stack()
        self.greenlet = greenlet.getcurrent()
        super(DebugListener, self).__init__(evtype, fileno, cb)
    def __repr__(self):
        return "DebugListener(%r, %r, %r, %r)\n%sEndDebugFdListener" % (self.evtype,
                                                                        self.fileno,
                                                                        self.cb,
                                                                        self.greenlet,
                                                                        ''.join(self.where_called))
    __str__ = __repr__
    

class BaseHub(object):
    """ Base hub class for easing the implementation of subclasses that are
    specific to a particular underlying event architecture. """

    SYSTEM_EXCEPTIONS = (KeyboardInterrupt, SystemExit)
    
    READ = READ
    WRITE = WRITE

    def __init__(self, clock=time.time):
        self.listeners = {READ:{}, WRITE:{}}

        self.clock = clock
        self.greenlet = greenlet.greenlet(self.run)
        self.stopping = False
        self.running = False
        self.timers = []
        self.next_timers = []
        self.observers = {}
        self.observer_modes = {
            'entry': [],
            'before_timers': [],
            'before_waiting': [],
            'after_waiting': [],
            'exit': [],
        }
        self.lclass = FdListener
        self.debug_exceptions = True
        
    def add(self, evtype, fileno, cb):
        """ Signals an intent to or write a particular file descriptor.

        The *evtype* argument is either the constant READ or WRITE.

        The *fileno* argument is the file number of the file of interest.

        The *cb* argument is the callback which will be called when the file
        is ready for reading/writing.
        """
        listener = self.lclass(evtype, fileno, cb)
        self.listeners[evtype].setdefault(fileno, []).append(listener)
        return listener

    def remove(self, listener):
        listener_list = self.listeners[listener.evtype].pop(listener.fileno, [])
        try:
            listener_list.remove(listener)
        except ValueError:
            pass
        if listener_list:
            self.listeners[listener.evtype][listener.fileno] = listener_list
        
    def remove_descriptor(self, fileno):
        """ Completely remove all listeners for this fileno.  For internal use 
        only."""
        self.listeners[READ].pop(fileno, None)
        self.listeners[WRITE].pop(fileno, None)

    def stop(self):
        self.abort()
        if self.greenlet is not greenlet.getcurrent():
            self.switch()

    def switch(self):
        cur = greenlet.getcurrent()
        assert cur is not self.greenlet, 'Cannot switch to MAINLOOP from MAINLOOP'
        switch_out = getattr(cur, 'switch_out', None)
        if switch_out is not None:
            try:
                switch_out()
            except:
                traceback.print_exception(*sys.exc_info())
        if self.greenlet.dead:
            self.greenlet = greenlet.greenlet(self.run)
        try:
            greenlet.getcurrent().parent = self.greenlet
        except ValueError:
            pass
        return self.greenlet.switch()

    def squelch_exception(self, fileno, exc_info):
        traceback.print_exception(*exc_info)
        sys.stderr.write("Removing descriptor: %r\n" % (fileno,))
        sys.stderr.flush()
        try:
            self.remove_descriptor(fileno)
        except Exception, e:
            sys.stderr.write("Exception while removing descriptor! %r\n" % (e,))
            sys.stderr.flush()

    def wait(self, seconds=None):
        raise NotImplementedError("Implement this in a subclass")

    def default_sleep(self):
        return 60.0

    def sleep_until(self):
        t = self.timers
        if not t:
            return None
        return t[0][0]

    def run(self):
        """Run the runloop until abort is called.
        """
        if self.running:
            raise RuntimeError("Already running!")
        try:
            self.running = True
            self.stopping = False
            self.fire_observers('entry')
            while not self.stopping:
                self.prepare_timers()
                self.fire_observers('before_timers')
                self.fire_timers(self.clock())
                self.prepare_timers()
                wakeup_when = self.sleep_until()
                if wakeup_when is None:
                    sleep_time = self.default_sleep()
                else:
                    sleep_time = wakeup_when - self.clock()
                if sleep_time > 0:
                    self.fire_observers('before_waiting')
                    self.wait(sleep_time)
                    self.fire_observers('after_waiting')
                else:
                    self.wait(0)
            else:
                del self.timers[:]
                del self.next_timers[:]
            self.fire_observers('exit')
        finally:
            self.running = False
            self.stopping = False

    def abort(self):
        """Stop the runloop. If run is executing, it will exit after completing
        the next runloop iteration.
        """
        if self.running:
            self.stopping = True

    def add_observer(self, observer, *modes):
        """Add an event observer to this runloop with the given modes.
        Valid modes are:
            entry: The runloop is being entered.
            before_timers: Before the expired timers for this iteration are executed.
            before_waiting: Before waiting for the calculated wait_time
                where nothing will happen.
            after_waiting: After waiting, immediately before starting the top of the
                runloop again.
            exit: The runloop is exiting.

        If no mode is passed or mode is all, the observer will be fired for every
        event type.
        """
        if not modes or modes == ('all',):
            modes = tuple(self.observer_modes)
        self.observers[observer] = modes
        for mode in modes:
            self.observer_modes[mode].append(observer)

    def remove_observer(self, observer):
        """Remove a previously registered observer from all event types.
        """
        for mode in self.observers.pop(observer, ()):
            self.observer_modes[mode].remove(observer)

    def squelch_observer_exception(self, observer, exc_info):
        traceback.print_exception(*exc_info)
        sys.stderr.write("Removing observer: %r\n" % (observer,))
        sys.stderr.flush()
        self.remove_observer(observer)

    def fire_observers(self, activity):
        for observer in self.observer_modes[activity]:
            try:
                observer(self, activity)
            except self.SYSTEM_EXCEPTIONS:
                raise
            except:
                self.squelch_observer_exception(observer, sys.exc_info())

    def squelch_generic_exception(self, exc_info):
        if self.debug_exceptions:
            traceback.print_exception(*exc_info)
            sys.stderr.flush()

    def squelch_timer_exception(self, timer, exc_info):
        if self.debug_exceptions:
            traceback.print_exception(*exc_info)
            sys.stderr.flush()

    def _add_absolute_timer(self, when, info):
        # the 0 placeholder makes it easy to bisect_right using (now, 1)
        self.next_timers.append((when, 0, info))

    def add_timer(self, timer):
        scheduled_time = self.clock() + timer.seconds
        self._add_absolute_timer(scheduled_time, timer)
        return scheduled_time

    def timer_finished(self, timer):
        pass

    def timer_canceled(self, timer):
        self.timer_finished(timer)

    def prepare_timers(self):
        ins = bisect.insort_right
        t = self.timers
        for item in self.next_timers:
            ins(t, item)
        del self.next_timers[:]

    def schedule_call_local(self, seconds, cb, *args, **kw):
        """Schedule a callable to be called after 'seconds' seconds have
        elapsed. Cancel the timer if greenlet has exited.
            seconds: The number of seconds to wait.
            cb: The callable to call after the given time.
            *args: Arguments to pass to the callable when called.
            **kw: Keyword arguments to pass to the callable when called.
        """
        t = LocalTimer(seconds, cb, *args, **kw)
        self.add_timer(t)
        return t

    def schedule_call_global(self, seconds, cb, *args, **kw):
        """Schedule a callable to be called after 'seconds' seconds have
        elapsed. The timer will NOT be cancelled if the current greenlet has
        exited before the timer fires.
            seconds: The number of seconds to wait.
            cb: The callable to call after the given time.
            *args: Arguments to pass to the callable when called.
            **kw: Keyword arguments to pass to the callable when called.
        """
        t = Timer(seconds, cb, *args, **kw)
        self.add_timer(t)
        return t

    def fire_timers(self, when):
        t = self.timers
        last = bisect.bisect_right(t, (when, 1))
        i = 0
        for i in xrange(last):
            timer = t[i][2]
            try:
                try:
                    timer()
                except self.SYSTEM_EXCEPTIONS:
                    raise
                except:
                    self.squelch_timer_exception(timer, sys.exc_info())
            finally:
                self.timer_finished(timer)
        del t[:last]

    # for debugging:

    def get_readers(self):
        return self.listeners[READ].values()

    def get_writers(self):
        return self.listeners[WRITE].values()

    def get_timers_count(hub):
        return max(len(hub.timers), len(hub.next_timers))
        
    def set_debug_listeners(self, value):
        if value:
            self.lclass = DebugListener
        else:
            self.lclass = FdListener
            
    def set_timer_exceptions(self, value):
        self.debug_exceptions = value
