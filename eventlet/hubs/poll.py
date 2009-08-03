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

    def add_reader(self, fileno, read_cb):
        """ Signals an intent to read from a particular file descriptor.

        The *fileno* argument is the file number of the file of interest.

        The *read_cb* argument is the callback which will be called when the file
        is ready for reading.
        """
        oldreader = self.readers.get(fileno)
        super(Hub, self).add_reader(fileno, read_cb)

        if not oldreader:
            # Only need to re-register this fileno if the mask changes
            mask = self.get_fn_mask(oldreader, self.writers.get(fileno))
            self.poll.register(fileno, mask)
            
    def add_writer(self, fileno, write_cb):
        """ Signals an intent to write to a particular file descriptor.

        The *fileno* argument is the file number of the file of interest.

        The *write_cb* argument is the callback which will be called when the file
        is ready for writing.
        """
        oldwriter = self.writer.get(fileno)
        super(Hub, self).add_writer(fileno, write_cb)

        if not oldwriter:
            # Only need to re-register this fileno if the mask changes
            mask = self.get_fn_mask(oldwriter, self.readers.get(fileno))
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
        try:
            self.poll.unregister(fileno)
        except KeyError:
            pass

    def wait(self, seconds=None):
        readers = self.readers
        writers = self.writers

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
            for dct, mask in ((readers, READ_MASK), (writers, WRITE_MASK)):
                cb = dct.get(fileno)
                func = None
                if cb is not None and event & mask:
                    func = cb
                if func:
                    try:
                        func(fileno)
                    except SYSTEM_EXCEPTIONS:
                        raise
                    except:
                        self.squelch_exception(fileno, sys.exc_info())
