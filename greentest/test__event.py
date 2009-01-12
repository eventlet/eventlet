# Copyright (c) 2008 Denis Bilenko
#
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

from __future__ import with_statement
import unittest
from eventlet.coros import event
from eventlet.api import spawn, sleep, exc_after, timeout

DELAY= 0.01

class TestEvent(unittest.TestCase):
    
    def test_send_exc(self):
        log = []
        e = event()

        def waiter():
            try:
                result = e.wait()
                log.append(('received', result))
            except Exception, ex:
                log.append(('catched', type(ex).__name__))
        spawn(waiter)
        sleep(0) # let waiter to block on e.wait()
        e.send(exc=Exception())
        sleep(0)
        assert log == [('catched', 'Exception')], log

    def test_send(self):
        event1 = event()
        event2 = event()

        spawn(event1.send, 'hello event1')
        exc_after(0, ValueError('interrupted'))
        try:
            result = event1.wait()
        except ValueError:
            with timeout(DELAY, None):
                result = event2.wait()
                raise AssertionError('Nobody sent anything to event2 yet it received %r' % (result, ))


if __name__=='__main__':
    unittest.main()
