from tests import patcher_test

psycopg_test_file = """
import sys
import eventlet
eventlet.monkey_patch()
from eventlet import patcher
if not patcher.is_monkey_patched('psycopg'):
    print "Psycopg not monkeypatched"
    sys.exit(0)

count = [0]
def tick(totalseconds, persecond):
    for i in xrange(totalseconds*persecond):
        count[0] += 1
        eventlet.sleep(1.0/persecond)
        
import psycopg2    
def fetch(num, secs):
    conn = psycopg2.connect()
    cur = conn.cursor()
    for i in range(num):
        cur.execute("select pg_sleep(%s)", (secs,))

f = eventlet.spawn(fetch, 2, 1)
t = eventlet.spawn(tick, 2, 100)
f.wait()
assert count[0] > 150
print "done"
"""

class PatchingPsycopg(patcher_test.Patcher):
    def test_psycopg_pached(self):
        self.write_to_tempfile("psycopg_patcher", psycopg_test_file)
        output, lines = self.launch_subprocess('psycopg_patcher.py')
        if lines[0].startswith('Psycopg not monkeypatched'):
            print "Can't test psycopg2 patching; it's not installed."
            return
        # if there's anything wrong with the test program it'll have a stack trace
        self.assert_(lines[0].startswith('done'), repr(output))

