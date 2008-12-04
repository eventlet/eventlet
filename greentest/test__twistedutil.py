import sys
import unittest
from twisted.internet.error import DNSLookupError
from twisted.internet import defer
from twisted.python.failure import Failure
from eventlet.twistedutil import block_on
from eventlet.api import get_hub
from greentest.test_support import exit_disabled

if 'Twisted' not in type(get_hub()).__name__:
    exit_disabled()

class Test(unittest.TestCase):

    def test_block_on_success(self):
        from twisted.internet import reactor
        d = reactor.resolver.getHostByName('www.google.com')
        ip = block_on(d)
        assert len(ip.split('.'))==4, ip
        ip2 = block_on(d)
        assert ip == ip2, (ip, ip2)
 
    def test_block_on_fail(self):
        from twisted.internet import reactor
        d = reactor.resolver.getHostByName('xxx')
        self.assertRaises(DNSLookupError, block_on, d)
 
    def test_block_on_already_succeed(self):
        d = defer.succeed('hey corotwine')
        res = block_on(d)
        assert res == 'hey corotwine', `res`

    def test_block_on_already_failed(self):
        d = defer.fail(Failure(ZeroDivisionError()))
        self.assertRaises(ZeroDivisionError, block_on, d)

if __name__=='__main__':
    unittest.main()

