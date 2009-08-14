# @author Bob Ippolito
#
# Copyright (c) 2005-2006, Bob Ippolito
# Copyright (c) 2007, Linden Research, Inc.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import sys
import select
import errno
from time import sleep
import time

from eventlet.hubs import hub

EXC_MASK = select.POLLERR | select.POLLHUP | select.POLLNVAL
READ_MASK = select.POLLIN
WRITE_MASK = select.POLLOUT

class Hub(hub.BaseHub):
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
        if self.listeners['read'].get(fileno):
            mask |= READ_MASK
        if self.listeners['write'].get(fileno):
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
        readers = self.listeners['read']
        writers = self.listeners['write']

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
