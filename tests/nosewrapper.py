""" This script simply gets the paths correct for testing eventlet with the 
hub extension for Nose."""
import nose
from os.path import dirname, realpath, abspath
import sys

parent_dir = dirname(dirname(realpath(abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# hacky hacks: skip test__api_timeout when under 2.4 because otherwise it SyntaxErrors
if sys.version_info < (2,5):
    argv = sys.argv + ["--exclude=.*test__api_timeout.*"]
else:
    argv = sys.argv

from tests import eventlethub
nose.main(addplugins=[eventlethub.EventletHub()], argv=argv)
