import os
import tempfile
import subprocess
import sys

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
patcher.inject('%s', globals(), ('socket', socket), ('urllib', urllib))
del patcher
"""

import_module_contents = """
import %(mod)s
import httplib
print "importing", %(mod)s, httplib, %(mod)s.socket, %(mod)s.urllib
"""

class Patcher(LimitedTestCase):
    TEST_TIMEOUT=3 # starting processes is time-consuming
    def setUp(self):
        self._saved_syspath = sys.path
        self.tempfiles = []
        
    def tearDown(self):
        sys.path = self._saved_syspath
        for tf in self.tempfiles:
            os.remove(tf)
        
    def write_to_tempfile(self, contents):
        fn, filename = tempfile.mkstemp('_patcher_test.py')
        fd = os.fdopen(fn, 'w')
        fd.write(contents)
        fd.close()
        self.tempfiles.append(filename)
        return os.path.dirname(filename), os.path.basename(filename)

    def test_patch_a_module(self):
        base = self.write_to_tempfile(base_module_contents)
        base_modname = os.path.splitext(base[1])[0]
        patching = self.write_to_tempfile(patching_module_contents % base_modname)
        patching_modname = os.path.splitext(patching[1])[0]
        importing = self.write_to_tempfile(
            import_module_contents % dict(mod=patching_modname))
        
        python_path = os.pathsep.join(sys.path)
        python_path += os.pathsep.join((base[0], patching[0], importing[0]))
        new_env = os.environ.copy()
        new_env['PYTHONPATH'] = python_path
        p = subprocess.Popen([sys.executable, 
                    os.path.join(importing[0], importing[1])],
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