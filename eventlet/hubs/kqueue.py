import sys
from eventlet import patcher
select = patcher.original('select')
time = patcher.original('time')
sleep = time.sleep

from eventlet.support import clear_sys_exc_info
from eventlet.hubs.hub import BaseHub, READ, WRITE, noop


if getattr(select, 'kqueue', None) is None:
    raise ImportError('No kqueue implementation found in select module')


FILTERS = {READ: select.KQ_FILTER_READ,
           WRITE: select.KQ_FILTER_WRITE}


class Hub(BaseHub):
    MAX_EVENTS = 100

    def __init__(self, clock=time.time):
        super(Hub, self).__init__(clock)
        self._events = {}
        self.kqueue = select.kqueue()

    def add(self, evtype, fileno, cb):
        listener = super(Hub, self).add(evtype, fileno, cb)
        events = self._events.setdefault(fileno, {})
        if evtype not in events:
            try:
                event = select.kevent(fileno,
                                      FILTERS.get(evtype), select.KQ_EV_ADD)
                self.kqueue.control([event], 0, 0)
                events[evtype] = event
            except ValueError:
                super(Hub, self).remove(listener)
                raise
        return listener

    def _delete_events(self, events):
        del_events = map(lambda e: select.kevent(e.ident, e.filter,
                         select.KQ_EV_DELETE), events)
        self.kqueue.control(del_events, 0, 0)

    def remove(self, listener):
        super(Hub, self).remove(listener)
        evtype = listener.evtype
        fileno = listener.fileno
        if not self.listeners[evtype].get(fileno):
            event = self._events[fileno].pop(evtype)
            try:
                self._delete_events([event])
            except OSError, e:
                pass

    def remove_descriptor(self, fileno):
        super(Hub, self).remove_descriptor(fileno)
        try:
            events = self._events.pop(fileno).values()
            self._delete_events(events)
        except KeyError, e:
            pass
        except OSError, e:
            pass

    def wait(self, seconds=None):
        readers = self.listeners[READ]
        writers = self.listeners[WRITE]

        if not readers and not writers:
            if seconds:
                sleep(seconds)
            return
        result = self.kqueue.control([], self.MAX_EVENTS, seconds)
        SYSTEM_EXCEPTIONS = self.SYSTEM_EXCEPTIONS
        for event in result:
            fileno = event.ident
            evfilt = event.filter
            try:
                if evfilt == FILTERS[READ]:
                    readers.get(fileno, noop).cb(fileno)
                if evfilt == FILTERS[WRITE]:
                    writers.get(fileno, noop).cb(fileno)
            except SYSTEM_EXCEPTIONS:
                raise
            except:
                self.squelch_exception(fileno, sys.exc_info())
                clear_sys_exc_info()
