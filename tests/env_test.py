import os
from tests.patcher_test import ProcessBase
from tests import skip_with_pyevent

class Socket(ProcessBase):
    def test_patched_thread(self):
        new_mod = """from eventlet.green import socket
socket.gethostbyname('localhost')
socket.getaddrinfo('localhost', 80)
"""
        os.environ['EVENTLET_TPOOL_DNS'] = 'yes'
        try:
            self.write_to_tempfile("newmod", new_mod)
            output, lines = self.launch_subprocess('newmod.py')
            self.assertEqual(len(lines), 1, lines)
        finally:
            del os.environ['EVENTLET_TPOOL_DNS']

class Tpool(ProcessBase):
    @skip_with_pyevent
    def test_tpool_size(self):
        new_mod = """from eventlet import tpool
import eventlet
import time
current = [0]
highwater = [0]
def count():
    current[0] += 1
    time.sleep(0.04)
    if current[0] > highwater[0]:
        highwater[0] = current[0]
    current[0] -= 1
expected = 40
p = eventlet.GreenPool()
for i in xrange(expected):
    p.spawn(tpool.execute,count)
p.waitall()
assert highwater[0] == expected, "%s != %s" % (highwater[0], expected)"""
        os.environ['EVENTLET_THREADPOOL_SIZE'] = "40"
        try:
            self.write_to_tempfile("newmod", new_mod)
            output, lines = self.launch_subprocess('newmod.py')
            self.assertEqual(len(lines), 1, lines)
        finally:
            del os.environ['EVENTLET_THREADPOOL_SIZE']

class Hub(ProcessBase):
    def test_eventlet_hub(self):
        new_mod = """from eventlet import hubs
print hubs.get_hub()
"""
        os.environ['EVENTLET_HUB'] = 'selects'
        try:
            self.write_to_tempfile("newmod", new_mod)
            output, lines = self.launch_subprocess('newmod.py')
            self.assertEqual(len(lines), 2, "\n".join(lines))
            self.assert_("selects" in lines[0])
        finally:
            del os.environ['EVENTLET_HUB']
