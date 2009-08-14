from test import test_urllib2

from eventlet.green import socket
from eventlet.green import urllib2
from eventlet.green.urllib2 import Request, OpenerDirector

test_urllib2.socket = socket
test_urllib2.urllib2 = urllib2
test_urllib2.Request = Request
test_urllib2.OpenerDirector = OpenerDirector

from test.test_urllib2 import *

if __name__ == "__main__":
    test_main()
