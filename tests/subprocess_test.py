import eventlet
from eventlet.green import subprocess
import eventlet.patcher
import os
import sys
import time
original_subprocess = eventlet.patcher.original('subprocess')


def test_subprocess_wait():
	# https://bitbucket.org/eventlet/eventlet/issue/89
	# In Python 3.3 subprocess.Popen.wait() method acquired `timeout`
	# argument.
	# RHEL backported it to their Python 2.6 package.
	p = subprocess.Popen([sys.executable,
	                     "-c", "import time; time.sleep(0.5)"])
	ok = False
	t1 = time.time()
	try:
		p.wait(timeout=0.1)
	except subprocess.TimeoutExpired:
		ok = True
	tdiff = time.time() - t1
	assert ok == True, 'did not raise subprocess.TimeoutExpired'
	assert 0.1 <= tdiff <= 0.2, 'did not stop within allowed time'
