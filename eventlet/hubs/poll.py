"""\
@file poll.py
@author Bob Ippolito

Copyright (c) 2005-2006, Bob Ippolito
Copyright (c) 2007, Linden Research, Inc.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import sys
import select
import socket
import errno
import traceback
from time import sleep
import time

from eventlet import greenlib
from eventlet.hubs import hub

EXC_MASK = select.POLLERR | select.POLLHUP | select.POLLNVAL
READ_MASK = select.POLLIN
WRITE_MASK = select.POLLOUT

class Hub(hub.BaseHub):
    def __init__(self, clock=time.time):
        super(Hub, self).__init__(clock)
        self.poll = select.poll()

    def add_descriptor(self, fileno, read=None, write=None, exc=None):
        super(Hub, self).add_descriptor(fileno, read, write, exc)

        mask = self.get_fn_mask(read, write)
        oldmask = self.get_fn_mask(self.readers.get(fileno), self.writers.get(fileno))
        if mask != oldmask:
            # Only need to re-register this fileno if the mask changes
            self.poll.register(fileno, mask)

    def get_fn_mask(self, read, write):
        mask = 0
        if read is not None:
            mask |= READ_MASK
        if write is not None:
            mask |= WRITE_MASK
        return mask

        
    def remove_descriptor(self, fileno):
        super(Hub, self).remove_descriptor(fileno)
        self.poll.unregister(fileno)
        
    def wait(self, seconds=None):
        readers = self.readers
        writers = self.writers
        excs = self.excs
        
        if not readers and not writers and not excs:
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
            for dct, mask in ((readers, READ_MASK), (writers, WRITE_MASK), (excs, EXC_MASK)):
                func = dct.get(fileno)
                if func is not None and event & mask:
                    try:
                        func(fileno)
                    except SYSTEM_EXCEPTIONS:
                        raise
                    except:
                        self.squelch_exception(fileno, sys.exc_info())
