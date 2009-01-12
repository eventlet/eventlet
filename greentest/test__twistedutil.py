# Copyright (c) 2008 AG Projects
# Author: Denis Bilenko
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from twisted.internet import reactor
from greentest import exit_unless_twisted
exit_unless_twisted()
import unittest
from twisted.internet.error import DNSLookupError
from twisted.internet import defer
from twisted.python.failure import Failure
from eventlet.twistedutil import block_on

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

