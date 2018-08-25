import errno
import math
import signal
import sys
import traceback

arm_alarm = None
if hasattr(signal, 'setitimer'):
    def alarm_itimer(seconds):
        signal.setitimer(signal.ITIMER_REAL, seconds)
    arm_alarm = alarm_itimer
else:
    try:
        import itimer
        arm_alarm = itimer.alarm
    except ImportError:
        def alarm_signal(seconds):
            signal.alarm(math.ceil(seconds))
        arm_alarm = alarm_signal

from eventlet.hubs import timer, IOClosed
from eventlet.support import greenlets as greenlet, clear_sys_exc_info
from eventlet.green import time as green_time
import inspect

g_prevent_multiple_readers = True

READ = "read"
WRITE = "write"


def closed_callback(fileno):
    """ Used to de-fang a callback that may be triggered by a loop in BaseHub.wait
    """
    # No-op.
    pass


class FdListener(object):
    __slots__ = ['evtype', 'fileno', 'cb', 'tb', 'mark_as_closed', 'spent', 'greenlet']

    def __init__(self, *args):
        """
        *args: 'evtype', 'fileno', 'cb', 'tb', 'mark_as_closed'

        The following are required:
        cb - the standard callback, which will switch into the
            listening greenlet to indicate that the event waited upon
            is ready
        tb - a 'throwback'. This is typically greenlet.throw, used
            to raise a signal into the target greenlet indicating that
            an event was obsoleted by its underlying filehandle being
            repurposed.
        mark_as_closed - if any listener is obsoleted, this is called
            (in the context of some other client greenlet) to alert
            underlying filehandle-wrapping objects that they've been
            closed.
        """
        self.evtype, self.fileno, self.cb, self.tb, self.mark_as_closed = args
        assert (self.evtype is READ or self.evtype is WRITE)
        self.spent = False
        self.greenlet = greenlet.getcurrent()

    def __repr__(self):
        return "%s(%r, %r, %r, %r)" % (type(self).__name__, self.evtype, self.fileno, self.cb, self.tb)
    __str__ = __repr__

    def defang(self):
        self.cb = closed_callback
        if self.mark_as_closed is not None:
            self.mark_as_closed()
        self.spent = True


noop = FdListener(READ, 0, lambda x: None, lambda x: None, None)


# in debug mode, track the call site that created the listener


class DebugListener(FdListener):
    __slots__ = FdListener.__slots__ + ['where_called']

    def __init__(self, evtype, fileno, cb, tb, mark_as_closed):
        super(DebugListener, self).__init__(evtype, fileno, cb, tb, mark_as_closed)
        self.where_called = traceback.format_stack()

    def __repr__(self):
        return "DebugListener(%r, %r, %r, %r, %r, %r)\n%sEndDebugFdListener" % (
            self.evtype,
            self.fileno,
            self.cb,
            self.tb,
            self.mark_as_closed,
            self.greenlet,
            ''.join(self.where_called))
    __str__ = __repr__


def alarm_handler(signum, frame):
    raise RuntimeError("Blocking detector ALARMED at" + str(inspect.getframeinfo(frame)))


class BaseHub(object):
    """ Base hub class for easing the implementation of subclasses that are
    specific to a particular underlying event architecture. """

    SYSTEM_EXCEPTIONS = (KeyboardInterrupt, SystemExit)
    READ = READ
    WRITE = WRITE

    def __init__(self, clock=None):
        self.listeners_r = {}
        self.listeners_w = {}
        self.secondaries_r = {}
        self.secondaries_w = {}

        self.listeners = {READ: self.listeners_r, WRITE: self.listeners_w}  # compatibilities usages / ev_type access
        self.secondaries = {READ: self.secondaries_r, WRITE: self.secondaries_w}
        self.closed = []

        self.clock = green_time.monotonic if clock is None else clock

        self.greenlet = greenlet.greenlet(self.run)
        self.stopping = False
        self.running = False
        self.timers = []
        self.lclass = FdListener
        self._old_signal_handler = False
        self.debug_exceptions = True
        self.debug_blocking = False
        self.debug_blocking_resolution = 1

    def block_detect_pre(self):
        # shortest alarm we can possibly raise is one second
        tmp = signal.signal(signal.SIGALRM, alarm_handler)
        if tmp != alarm_handler:
            self._old_signal_handler = tmp

        arm_alarm(self.debug_blocking_resolution)

    def block_detect_post(self):
        if self._old_signal_handler:
            signal.signal(signal.SIGALRM, self._old_signal_handler)
        signal.alarm(0)

    def add(self, evtype, fileno, cb, tb, mark_as_closed):
        """ Signals an intent to or write a particular file descriptor.

        The *evtype* argument is either the constant READ or WRITE.

        The *fileno* argument is the file number of the file of interest.

        The *cb* argument is the callback which will be called when the file
        is ready for reading/writing.

        The *tb* argument is the throwback used to signal (into the greenlet)
        that the file was closed.

        The *mark_as_closed* is used in the context of the event hub to
        prepare a Python object as being closed, pre-empting further
        close operations from accidentally shutting down the wrong OS thread.
        """
        listener = self.lclass(evtype, fileno, cb, tb, mark_as_closed)
        bucket = self.listeners[evtype]
        if fileno in bucket:
            if g_prevent_multiple_readers:
                raise RuntimeError(
                    "Second simultaneous %s on fileno %s "
                    "detected.  Unless you really know what you're doing, "
                    "make sure that only one greenthread can %s any "
                    "particular socket.  Consider using a pools.Pool. "
                    "If you do know what you're doing and want to disable "
                    "this error, call "
                    "eventlet.debug.hub_prevent_multiple_readers(False) - MY THREAD=%s; "
                    "THAT THREAD=%s" % (
                        evtype, fileno, evtype, cb, bucket[fileno]))
            # store off the second listener in another structure
            self.secondaries[evtype].setdefault(fileno, []).append(listener)
        else:
            bucket[fileno] = listener
        return listener

    def _obsolete(self, fileno):
        """ We've received an indication that 'fileno' has been obsoleted.
            Any current listeners must be defanged, and notifications to
            their greenlets queued up to send.
        """
        found = False
        if fileno in self.secondaries_w:
            for listener in self.secondaries_w.pop(fileno):
                found = True
                self.closed.append(listener)
                listener.defang()
        if fileno in self.secondaries_r:
            for listener in self.secondaries_r.pop(fileno):
                found = True
                self.closed.append(listener)
                listener.defang()

        # For the primary listeners, we actually need to call remove,
        # which may modify the underlying OS polling objects.
        if fileno in self.listeners_w:
            listener = self.listeners_w[fileno]
            found = True
            self.closed.append(listener)
            self.remove(listener)
            listener.defang()
        if fileno in self.listeners_r:
            listener = self.listeners_r[fileno]
            found = True
            self.closed.append(listener)
            self.remove(listener)
            listener.defang()

        return found

    def notify_close(self, fileno):
        """ We might want to do something when a fileno is closed.
            However, currently it suffices to obsolete listeners only
            when we detect an old fileno being recycled, on open.
        """
        pass

    def remove(self, listener):
        if listener.spent:
            # trampoline may trigger this in its finally section.
            return

        fileno = listener.fileno
        evtype = listener.evtype
        self.listeners[evtype].pop(fileno, None)
        # migrate a secondary listener to be the primary listener
        sec = self.secondaries[evtype].get(fileno, None)
        if sec is None:
            return
        self.listeners[evtype][fileno] = sec.pop(0)
        if not sec:
            self.secondaries[evtype].pop(fileno)

    def mark_as_reopened(self, fileno):
        """ If a file descriptor is returned by the OS as the result of some
            open call (or equivalent), that signals that it might be being
            recycled.

            Catch the case where the fd was previously in use.
        """
        self._obsolete(fileno)

    def remove_descriptor(self, fileno):
        """ Completely remove all listeners for this fileno.  For internal use
        only."""

        listeners = []
        listener = self.listeners_r.pop(fileno, None)
        if listener:
            listeners.append(listener)
        listener = self.listeners_w.pop(fileno, None)
        if listener:
            listeners.append(listener)

        listeners.extend(self.secondaries_r.pop(fileno, ()))
        listeners.extend(self.secondaries_w.pop(fileno, ()))
        for listener in listeners:
            try:
                listener.cb(fileno)
            except Exception:
                self.squelch_generic_exception(sys.exc_info())

    def close_one(self):
        """ Triggered from the main run loop. If a listener's underlying FD was
            closed somehow, throw an exception back to the trampoline, which should
            be able to manage it appropriately.
        """
        listener = self.closed.pop()
        if not listener.greenlet.dead:
            # There's no point signalling a greenlet that's already dead.
            listener.tb(IOClosed(errno.ENOTCONN, "Operation on closed file"))

    def ensure_greenlet(self):
        if self.greenlet.dead:
            # create new greenlet sharing same parent as original
            new = greenlet.greenlet(self.run, self.greenlet.parent)
            # need to assign as parent of old greenlet
            # for those greenlets that are currently
            # children of the dead hub and may subsequently
            # exit without further switching to hub.
            self.greenlet.parent = new
            self.greenlet = new

    def switch(self):
        cur = greenlet.getcurrent()
        assert cur is not self.greenlet, 'Cannot switch to MAINLOOP from MAINLOOP'
        switch_out = getattr(cur, 'switch_out', None)
        if switch_out is not None:
            try:
                switch_out()
            except:
                self.squelch_generic_exception(sys.exc_info())
        self.ensure_greenlet()
        try:
            if self.greenlet.parent is not cur:
                cur.parent = self.greenlet
        except ValueError:
            pass  # gets raised if there is a greenlet parent cycle
        clear_sys_exc_info()
        return self.greenlet.switch()

    def squelch_exception(self, fileno, exc_info):
        traceback.print_exception(*exc_info)
        sys.stderr.write("Removing descriptor: %r\n" % (fileno,))
        sys.stderr.flush()
        try:
            self.remove_descriptor(fileno)
        except Exception as e:
            sys.stderr.write("Exception while removing descriptor! %r\n" % (e,))
            sys.stderr.flush()

    def wait(self, seconds=None):
        raise NotImplementedError("Implement this in a subclass")

    def default_sleep(self):
        return 60.0

    def sleep_until(self):
        if not self.timers:
            return None
        return self.timers[0][0]

    def run(self, *a, **kw):
        """Run the runloop until abort is called.
        """
        # accept and discard variable arguments because they will be
        # supplied if other greenlets have run and exited before the
        # hub's greenlet gets a chance to run
        if self.running:
            raise RuntimeError("Already running!")
        try:
            self.running = True
            self.stopping = False
            while not self.stopping:
                while self.closed:
                    # We ditch all of these first.
                    self.close_one()
                if self.debug_blocking:
                    self.block_detect_pre()
                self.fire_timers(self.clock())
                if self.debug_blocking:
                    self.block_detect_post()

                sleep_time = self.timers[0][0] - self.clock() if self.timers else 5.0
                self.wait(sleep_time if 5.0 > sleep_time > 0 else 5.0)

            else:
                del self.timers[:]
        finally:
            self.running = False
            self.stopping = False

    def abort(self, wait=False):
        """Stop the runloop. If run is executing, it will exit after
        completing the next runloop iteration.

        Set *wait* to True to cause abort to switch to the hub immediately and
        wait until it's finished processing.  Waiting for the hub will only
        work from the main greenthread; all other greenthreads will become
        unreachable.
        """
        if self.running:
            self.stopping = True
        if wait:
            assert self.greenlet is not greenlet.getcurrent(), "Can't abort with wait from inside the hub's greenlet."
            # schedule an immediate timer just so the hub doesn't sleep
            self.schedule_call_global(0, lambda: None)
            # switch to it; when done the hub will switch back to its parent,
            # the main greenlet
            self.switch()

    def squelch_generic_exception(self, exc_info):
        if self.debug_exceptions:
            traceback.print_exception(*exc_info)
            sys.stderr.flush()
            clear_sys_exc_info()

    def squelch_timer_exception(self, tmr, exc_info):
        if self.debug_exceptions:
            traceback.print_exception(*exc_info)
            sys.stderr.flush()
            clear_sys_exc_info()

    def add_timer(self, tmr):
        scheduled_time = self.clock() + tmr.seconds
        if not self.timers:
            self.timers.append((scheduled_time, tmr))
            return scheduled_time

        for i in range(0, len(self.timers)):
            nxt_sche = self.timers[i][0]
            if nxt_sche == scheduled_time:
                scheduled_time += 0.000000000001  # pico uniqueness in case an eq happen
            if nxt_sche < scheduled_time:
                continue
            self.timers.insert(i, (scheduled_time, tmr))
            break
        return scheduled_time

    def timer_canceled(self, tmr):
        for i in range(0, len(self.timers)):
            if tmr.scheduled_time != self.timers[i][0]:
                continue
            self.timers.pop(i)
            break

    def prepare_timers(self):
        return

    def schedule_call_local(self, seconds, cb, *args, **kw):
        """Schedule a callable to be called after 'seconds' seconds have
        elapsed. Cancel the timer if greenlet has exited.
            seconds: The number of seconds to wait.
            cb: The callable to call after the given time.
            *args: Arguments to pass to the callable when called.
            **kw: Keyword arguments to pass to the callable when called.
        """
        t = timer.LocalTimer(seconds, cb, *args, **kw)
        self.add_timer(t)
        return t

    def schedule_call_global(self, seconds, cb, *args, **kw):
        """Schedule a callable to be called after 'seconds' seconds have
        elapsed. The timer will NOT be canceled if the current greenlet has
        exited before the timer fires.
            seconds: The number of seconds to wait.
            cb: The callable to call after the given time.
            *args: Arguments to pass to the callable when called.
            **kw: Keyword arguments to pass to the callable when called.
        """
        t = timer.Timer(seconds, cb, *args, **kw)
        self.add_timer(t)
        return t

    def fire_timers(self, when):
        t = self.timers
        while t:
            exp, tmr = t[0]
            if when > exp:
                break
            t.pop(0)
            try:
                tmr()
            except self.SYSTEM_EXCEPTIONS:
                raise
            except:
                self.squelch_timer_exception(tmr, sys.exc_info())
                clear_sys_exc_info()

    # for debugging:

    def get_readers(self):
        return self.listeners_r.values()

    def get_writers(self):
        return self.listeners_w.values()

    def get_timers_count(self):
        return len(self.timers)

    def set_debug_listeners(self, value):
        self.lclass = DebugListener if value else FdListener

    def set_timer_exceptions(self, value):
        self.debug_exceptions = value
