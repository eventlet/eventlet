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
from eventlet.api import call_after, spawn, sleep

class test(unittest.TestCase):

    def setUp(self):
        self.lst = [1]

    def test_timer_fired(self):
        
        def func():
            call_after(0.1, self.lst.pop)
            sleep(0.2)

        spawn(func)
        assert self.lst == [1], self.lst
        sleep(0.3)
        assert self.lst == [], self.lst

    def test_timer_cancelled_upon_greenlet_exit(self):
        
        def func():
            call_after(0.1, self.lst.pop)

        spawn(func)
        assert self.lst == [1], self.lst
        sleep(0.2)
        assert self.lst == [1], self.lst

    def test_spawn_is_not_cancelled(self):

        def func():
            spawn(self.lst.pop)
            # exiting immediatelly, but self.lst.pop must be called
        spawn(func)
        sleep(0.1)
        assert self.lst == [], self.lst


if __name__=='__main__':
    unittest.main()

