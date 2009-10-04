import sys
from unittest import TestCase, main

from eventlet import processes, api

class TestEchoPool(TestCase):
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


class TestCatPool(TestCase):
    def setUp(self):
        api.sleep(0)
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


class TestDyingProcessesLeavePool(TestCase):
    def setUp(self):
        self.pool = processes.ProcessPool('echo', ['hello'], max_size=1)

    def test_dead_process_not_inserted_into_pool(self):
        proc = self.pool.get()
        try:
            try:
                result = proc.read()
                self.assertEquals(result, 'hello\n')
                result = proc.read()
            except processes.DeadProcess:
                pass
        finally:
            self.pool.put(proc)
        proc2 = self.pool.get()
        self.assert_(proc is not proc2)


if __name__ == '__main__':
    main()
