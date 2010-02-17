import os
import shutil
import subprocess
import sys
import tempfile

from tests import LimitedTestCase

base_module_contents = """
import socket
import urllib
print "base", socket, urllib
"""

patching_module_contents = """
from eventlet.green import socket
from eventlet.green import urllib
from eventlet import patcher
print 'patcher', socket, urllib
patcher.inject('base', globals(), ('socket', socket), ('urllib', urllib))
del patcher
"""

import_module_contents = """
import patching
import socket
print "importing", patching, socket, patching.socket, patching.urllib
"""

class Patcher(LimitedTestCase):
    TEST_TIMEOUT=3 # starting processes is time-consuming
    def setUp(self):
        self._saved_syspath = sys.path
        self.tempdir = tempfile.mkdtemp('_patcher_test')
        
    def tearDown(self):
        sys.path = self._saved_syspath
        shutil.rmtree(self.tempdir)
        
    def write_to_tempfile(self, name, contents):
        filename = os.path.join(self.tempdir, name + '.py')
        fd = open(filename, "w")
        fd.write(contents)
        fd.close()
        
    def launch_subprocess(self, filename):
        python_path = os.pathsep.join(sys.path + [self.tempdir])
        new_env = os.environ.copy()
        new_env['PYTHONPATH'] = python_path
        p = subprocess.Popen([sys.executable, 
                              os.path.join(self.tempdir, filename)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=new_env)
        return p

    def test_patch_a_module(self):
        self.write_to_tempfile("base", base_module_contents)
        self.write_to_tempfile("patching", patching_module_contents)
        self.write_to_tempfile("importing", import_module_contents)
        p = self.launch_subprocess('importing.py')
        output = p.communicate()
        lines = output[0].split("\n")
        self.assert_(lines[0].startswith('patcher'))
        self.assert_(lines[1].startswith('base'))
        self.assert_(lines[2].startswith('importing'))
        self.assert_('eventlet.green.socket' in lines[1])
        self.assert_('eventlet.green.urllib' in lines[1])
        self.assert_('eventlet.green.socket' in lines[2])
        self.assert_('eventlet.green.urllib' in lines[2])
        self.assert_('eventlet.green.httplib' not in lines[2])
        
    def test_import_patched_defaults(self):
        self.write_to_tempfile("base", base_module_contents)
        new_mod = """
from eventlet import patcher
base = patcher.import_patched('base')
print "newmod", base, base.socket, base.urllib.socket.socket
"""
        self.write_to_tempfile("newmod", new_mod)
        p = self.launch_subprocess('newmod.py')
        output = p.communicate()
        lines = output[0].split("\n")
        self.assert_(lines[0].startswith('base'))
        self.assert_(lines[1].startswith('newmod'))
        self.assert_('eventlet.green.socket' in lines[1])
        self.assert_('GreenSocket' in lines[1])
        
    def test_monkey_patch(self):
        new_mod = """
from eventlet import patcher
patcher.monkey_patch()
import socket
import urllib
print "newmod", socket.socket, urllib.socket.socket
"""
        self.write_to_tempfile("newmod", new_mod)
        p = self.launch_subprocess('newmod.py')
        output = p.communicate()
        print output[0]
        lines = output[0].split("\n")
        self.assert_(lines[0].startswith('newmod'))
        self.assertEqual(lines[0].count('GreenSocket'), 2)
        
    def test_early_patching(self):
        new_mod = """
from eventlet import patcher
patcher.monkey_patch()
import eventlet
eventlet.sleep(0.01)
print "newmod"
"""
        self.write_to_tempfile("newmod", new_mod)
        p = self.launch_subprocess('newmod.py')
        output = p.communicate()
        print output[0]
        lines = output[0].split("\n")
        self.assertEqual(len(lines), 2)
        self.assert_(lines[0].startswith('newmod'))

    def test_late_patching(self):
        new_mod = """
import eventlet
eventlet.sleep(0.01)
from eventlet import patcher
patcher.monkey_patch()
eventlet.sleep(0.01)
print "newmod"
"""
        self.write_to_tempfile("newmod", new_mod)
        p = self.launch_subprocess('newmod.py')
        output = p.communicate()
        print output[0]
        lines = output[0].split("\n")
        self.assertEqual(len(lines), 2)
        self.assert_(lines[0].startswith('newmod'))
        
    def test_tpool(self):
        new_mod = """
import eventlet
from eventlet import patcher
patcher.monkey_patch()
from eventlet import tpool
print "newmod", tpool.execute(len, "hi")
print "newmod", tpool.execute(len, "hi2")
"""
        self.write_to_tempfile("newmod", new_mod)
        p = self.launch_subprocess('newmod.py')
        output = p.communicate()
        print output[0]
        lines = output[0].split("\n")
        self.assertEqual(len(lines), 3)
        self.assert_(lines[0].startswith('newmod'))
        self.assert_('2' in lines[0])
        self.assert_('3' in lines[1])
        
