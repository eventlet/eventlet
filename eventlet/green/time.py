from __future__ import absolute_import
from time import *
from eventlet.api import sleep

def _install():
    import time
    time.sleep = sleep
