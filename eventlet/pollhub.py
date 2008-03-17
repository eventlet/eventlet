"""\
@file pollhub.py
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

from eventlet import greenlib
from eventlet import hub

EXC_MASK = select.POLLERR | select.POLLHUP | select.POLLNVAL
READ_MASK = select.POLLIN
WRITE_MASK = select.POLLOUT

class Hub(hub.Hub):
    def __init__(self):
        super(Hub, self).__init__()
        self.poll = select.poll()

    def process_queue(self):
        readers = self.readers
        writers = self.writers
        excs = self.excs
        
        reg = self.poll.register
        unreg = self.poll.unregister
        rm = READ_MASK
        wm = WRITE_MASK
        for fileno, rwe in self.descriptor_queue.iteritems():
            read, write, exc = rwe
            if read is None and write is None and exc is None:
                for dct in (readers, writers, excs):
                    dct.pop(fileno, None)
                try:
                    unreg(fileno)
                except socket.error:
                    #print "squelched socket err on unreg", fileno
                    pass
            else:
                mask = 0
                if read is not None:
                    mask |= rm
                if write is not None:
                    mask |= wm
                oldmask = 0

                oldr = readers.get(fileno)
                oldw = writers.get(fileno)
                olde = excs.get(fileno)

                if oldr is not None:
                    oldmask |= rm
                if oldw is not None:
                    oldmask |= wm
                if mask != oldmask:
                    reg(fileno, mask)
                for op, dct in ((read, self.readers), (write, self.writers), (exc, self.excs)):
                    dct[fileno] = op
        self.descriptor_queue.clear()
        
    def wait(self, seconds=None):
        self.process_queue()
        
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
            read = readers.get(fileno)
            write = writers.get(fileno)
            exc = excs.get(fileno)

            if read is not None and event & READ_MASK:
                try:
                    read(fileno)
                except SYSTEM_EXCEPTIONS:
                    raise
                except:
                    self.squelch_exception(fileno, sys.exc_info())
            elif exc is not None and event & EXC_MASK:
                try:
                    exc(fileno)
                except SYSTEM_EXCEPTIONS:
                    raise
                except:
                    self.squelch_exception(fileno, sys.exc_info())

            if write is not None and event & WRITE_MASK:
                try:
                    write(fileno)
                except SYSTEM_EXCEPTIONS:
                    raise
                except:
                    self.squelch_exception(fileno, sys.exc_info())
