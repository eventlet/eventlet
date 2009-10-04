import sys
import select
import errno
from time import sleep
import time

from eventlet.hubs.hub import BaseHub, READ, WRITE

EXC_MASK = select.POLLERR | select.POLLHUP
READ_MASK = select.POLLIN
WRITE_MASK = select.POLLOUT

class Hub(BaseHub):
    def __init__(self, clock=time.time):
        super(Hub, self).__init__(clock)
        self.poll = select.poll()

    def add(self, evtype, fileno, cb):
        oldlisteners = self.listeners[evtype].get(fileno)
        
        listener = super(Hub, self).add(evtype, fileno, cb)
        if not oldlisteners:
            # Means we've added a new listener
            self.register(fileno)
        return listener
    
    def remove(self, listener):
        super(Hub, self).remove(listener)
        self.register(listener.fileno)

    def register(self, fileno):
        mask = 0
        if self.listeners[READ].get(fileno):
            mask |= READ_MASK
        if self.listeners[WRITE].get(fileno):
            mask |= WRITE_MASK
        if mask:
            self.poll.register(fileno, mask)
        else: 
            try:
                self.poll.unregister(fileno)
            except KeyError:
                pass

    def remove_descriptor(self, fileno):
        super(Hub, self).remove_descriptor(fileno)
        try:
            self.poll.unregister(fileno)
        except KeyError:
            pass

    def wait(self, seconds=None):
        readers = self.listeners[READ]
        writers = self.listeners[WRITE]

        if not readers and not writers:
            if seconds:
                sleep(seconds)
            return
        try:
            presult = self.poll.poll(seconds * 1000.0)
        except select.error, e:
            if e.args[0] == errno.EINTR:
                return
            raise
        SYSTEM_EXCEPTIONS = self.SYSTEM_EXCEPTIONS

        for fileno, event in presult:
            try:
                if event & READ_MASK:
                    readers[fileno][0](fileno)
                if event & WRITE_MASK:
                    writers[fileno][0](fileno)
                if event & select.POLLNVAL:
                    self.remove_descriptor(fileno)
                    continue
                if event & EXC_MASK:
                    for listeners in (readers.get(fileno, []), 
                                      writers.get(fileno, [])):
                        for listener in listeners:
                            listener(fileno)
            except KeyError:
                pass
            except SYSTEM_EXCEPTIONS:
                raise
            except:
                self.squelch_exception(fileno, sys.exc_info())
