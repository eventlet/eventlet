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
import time

from eventlet.hubs import hub

class Hub(hub.BaseHub):
    def _remove_closed_fds(self):
        """ Iterate through fds that have had their socket objects recently closed,
        removing the ones that are actually closed per the operating system.
        """
        for fd in self.closed_fds:
            try:
                select.select([fd], [], [], 0)
            except select.error, e:
                if e.args[0] == errno.EBADF:
                    self.remove_descriptor(fd)

    def wait(self, seconds=None):
        readers = self.listeners['read']
        writers = self.listeners['write']
        if not readers and not writers:
            if seconds:
                time.sleep(seconds)
            return
        try:
            print "waiting", readers, writers
            r, w, er = select.select(readers.keys(), writers.keys(), readers.keys() + writers.keys(), seconds)
            self.closed_fds = []
        except select.error, e:
            if e.args[0] == errno.EINTR:
                return
            elif e.args[0] == errno.EBADF:
                self._remove_closed_fds()
                self.closed_fds = []
                return
            else:
                raise

        for fileno in er:
            for r in readers.get(fileno):
                r(fileno)
            for w in writers.get(fileno):
                w(fileno)
            
        for listeners, events in ((readers, r), (writers, w)):
            for fileno in events:
                try:
                    l_list = listeners[fileno]
                    if l_list:
                        l_list[0](fileno)
                except self.SYSTEM_EXCEPTIONS:
                    raise
                except:
                    self.squelch_exception(fileno, sys.exc_info())
