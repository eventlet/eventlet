# Very rudimentary test of threading module

from eventlet.green import threading
from eventlet.green import thread
from eventlet.green import time

# need to override these modules before import so
# that classes inheriting from threading.Thread refer
# to the correct parent class
import sys
sys.modules['threading'] = threading

from test import test_threading
test_threading.thread = thread
test_threading.time = time

from test.test_threading import *

if __name__ == "__main__":
    test_main()