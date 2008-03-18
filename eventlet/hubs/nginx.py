"""\
@file nginx.py
@author Donovan Preston

Copyright (c) 2008, Linden Research, Inc.

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

from eventlet import greenlib
from eventlet.hubs import hub


WSGI_POLLIN = 0x01
WSGI_POLLOUT = 0x04


class Hub(hub.BaseHub):
    def add_descriptor(self, fileno, read=None, write=None, exc=None):
        super(Hub, self).add_descriptor(fileno, read, write, exc)

        if read is not None:
            self.poll_register(fileno, WSGI_POLLIN)
        elif write is not None:
            self.poll_register(fileno, WSGI_POLLOUT)
        
    def remove_descriptor(self, fileno):
        super(Hub, self).remove_descriptor(fileno)

        self.poll_unregister(fileno)
        
    def wait(self, seconds=None):
        if seconds is not None:
            self.sleep(int(seconds*1000))

        greenlib.switch(self.current_application)

