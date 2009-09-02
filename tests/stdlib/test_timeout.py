from eventlet.green import socket
from eventlet.green import time

from test import test_timeout

test_timeout.socket = socket
test_timeout.time = time

# to get past the silly 'requires' check
test_timeout.__name__ = '__main__'

from test.test_timeout import *

if __name__ == "__main__":
    test_main()