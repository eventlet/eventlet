import sys

import eventlet
from eventlet import debug
from eventlet import api
from tests import LimitedTestCase, main

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

class TestDebug(LimitedTestCase):
    def test_everything(self):
        debug.hub_exceptions(True)
        debug.hub_exceptions(False)
        debug.tpool_exceptions(True)
        debug.tpool_exceptions(False)
        debug.hub_listener_stacks(True)
        debug.hub_listener_stacks(False)
        debug.format_hub_listeners()

    def test_hub_exceptions(self):
        debug.hub_exceptions(True)
        server = api.tcp_listener(('0.0.0.0', 0))
        client = api.connect_tcp(('127.0.0.1', server.getsockname()[1]))
        client_2, addr = server.accept()
        
        def hurl(s):
            s.recv(1)
            {}[1]  # keyerror

        fake = StringIO()
        orig = sys.stderr
        sys.stderr = fake
        try:
            gt = eventlet.spawn(hurl, client_2)            
            eventlet.sleep(0)
            client.send(' ')
            eventlet.sleep(0)
        finally:
            sys.stderr = orig
            self.assertRaises(KeyError, gt.wait)
            debug.hub_exceptions(False)
        self.assert_('Traceback' in fake.getvalue(), 
            "Traceback not in:\n" + fake.getvalue())
        
if __name__ == "__main__":
    main()