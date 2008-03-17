"""\
@file processes_test.py
@author Donovan Preston, Aaron Brashears

Copyright (c) 2006-2007, Linden Research, Inc.
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
from eventlet import tests
from eventlet import api
from eventlet import channel
from eventlet import processes

class TestEchoPool(tests.TestCase):
    mode = 'static'
    def setUp(self):
        self.pool = processes.ProcessPool('echo', ["hello"])

    def test_echo(self):
        result = None

        proc = self.pool.get()
        try:
            result = proc.read()
        finally:
            self.pool.put(proc)
        self.assertEquals(result, 'hello\n')

    def test_read_eof(self):
        proc = self.pool.get()
        try:
            proc.read()
            self.assertRaises(processes.DeadProcess, proc.read)
        finally:
            self.pool.put(proc)


class TestCatPool(tests.TestCase):
    mode = 'static'
    def setUp(self):
        self.pool = processes.ProcessPool('cat')

    def test_cat(self):
        result = None

        proc = self.pool.get()
        try:
            proc.write('goodbye')
            proc.close_stdin()
            result = proc.read()
        finally:
            self.pool.put(proc)

        self.assertEquals(result, 'goodbye')

    def test_write_to_dead(self):
        result = None

        proc = self.pool.get()
        try:
            proc.write('goodbye')
            proc.close_stdin()
            result = proc.read()
            self.assertRaises(processes.DeadProcess, proc.write, 'foo')
        finally:
            self.pool.put(proc)

    def test_close(self):
        result = None

        proc = self.pool.get()
        try:
            proc.write('hello')
            proc.close()
            self.assertRaises(processes.DeadProcess, proc.write, 'goodbye')
        finally:
            self.pool.put(proc)


class TestDyingProcessesLeavePool(tests.TestCase):
    mode = 'static'
    def setUp(self):
        self.pool = processes.ProcessPool('echo', ['hello'], max_size=1)

    def test_dead_process_not_inserted_into_pool(self):
        proc = self.pool.get()
        try:
            result = proc.read()
            self.assertEquals(result, 'hello\n')
        finally:
            self.pool.put(proc)
        proc2 = self.pool.get()
        self.assert_(proc is not proc2)


class TestProcessLivesForever(tests.TestCase):
    mode = 'static'
    def setUp(self):
        self.pool = processes.ProcessPool('yes', max_size=1)

    def test_reading_twice_from_same_process(self):
        proc = self.pool.get()
        try:
            result = proc.read(2)
            self.assertEquals(result, 'y\n')
        finally:
            self.pool.put(proc)

        proc2 = self.pool.get()
        self.assert_(proc is proc2)
        try:
            result = proc2.read(2)
            self.assertEquals(result, 'y\n')
        finally:
            self.pool.put(proc2)


if __name__ == '__main__':
    tests.main()
