""" This script simply gets the paths correct for testing eventlet with the 
hub extension for Nose."""
import nose
from os.path import dirname, realpath, abspath
import sys

parent_dir = dirname(dirname(realpath(abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from tests import eventlethub
nose.main(addplugins=[eventlethub.EventletHub()])
