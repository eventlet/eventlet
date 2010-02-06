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

    def test_patch_a_module(self):
        self.write_to_tempfile("base", base_module_contents)
        self.write_to_tempfile("patching", patching_module_contents)
        self.write_to_tempfile("importing", import_module_contents)
        
        python_path = os.pathsep.join(sys.path + [self.tempdir])
        new_env = os.environ.copy()
        new_env['PYTHONPATH'] = python_path
        p = subprocess.Popen([sys.executable, 
                              os.path.join(self.tempdir, "importing.py")],
                stdout=subprocess.PIPE, env=new_env)
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
        python_path = os.pathsep.join(sys.path + [self.tempdir])
        new_env = os.environ.copy()
        new_env['PYTHONPATH'] = python_path
        p = subprocess.Popen([sys.executable, 
                              os.path.join(self.tempdir, "newmod.py")],
                stdout=subprocess.PIPE, env=new_env)
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
print "newmod", socket, urllib.socket.socket
"""
        self.write_to_tempfile("newmod", new_mod)
        python_path = os.pathsep.join(sys.path + [self.tempdir])
        new_env = os.environ.copy()
        new_env['PYTHONPATH'] = python_path
        p = subprocess.Popen([sys.executable, 
                              os.path.join(self.tempdir, "newmod.py")],
                stdout=subprocess.PIPE, env=new_env)
        output = p.communicate()
        lines = output[0].split("\n")
        self.assert_(lines[0].startswith('newmod'))
        self.assert_('eventlet.green.socket' in lines[0])
        self.assert_('GreenSocket' in lines[0])
