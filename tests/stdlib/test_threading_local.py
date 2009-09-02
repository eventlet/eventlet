from eventlet.green import thread
from eventlet.green import threading
from eventlet.green import time

from test import test_threading_local

test_threading_local.threading = threading

def test_main():
    import sys
    sys.modules['thread'] = thread
    sys.modules['threading'] = threading
    sys.modules['time'] = time
    test_threading_local.test_main()
    
if __name__ == '__main__':
    test_main()