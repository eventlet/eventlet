# Copyright (c) 2008 AG Projects
# Author: Denis Bilenko
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

import unittest
from eventlet.api import sleep, spawn, kill, with_timeout, TimeoutError

DELAY = 0.1

class Test(unittest.TestCase):

    def test_killing_dormant(self):
        state = []
        def test():
            try:
                state.append('start')
                sleep(DELAY)
            except:
                state.append('except')
                # catching GreenletExit
                pass
            # when switching to hub, hub makes itself the parent of this greenlet,
            # thus after the function's done, the control will go to the parent
            # QQQ why the first sleep is not enough?
            sleep(0)
            state.append('finished')
        g = spawn(test)
        sleep(DELAY/2)
        assert state == ['start'], state
        kill(g)
        # will not get there, unless switching is explicitly scheduled by kill
        assert state == ['start', 'except'], state
        sleep(DELAY)
        assert state == ['start', 'except', 'finished'], state

    def test_nested_with_timeout(self):
        def func():
            return with_timeout(0.2, sleep, 2, timeout_value=1)
        self.assertRaises(TimeoutError, with_timeout, 0.1, func)

if __name__=='__main__':
    unittest.main()

