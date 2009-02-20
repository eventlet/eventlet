# Copyright (c) 2008-2009 AG Projects
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
from twisted.names.srvconnect import SRVConnector
from gnutls.interfaces.twisted import X509Credentials

from eventlet.twistedutil.protocol import GreenClientCreator
from eventlet.twistedutil.protocols.basic import LineOnlyReceiverTransport

class NoisySRVConnector(SRVConnector):

    def pickServer(self):
        host, port = SRVConnector.pickServer(self)
        print 'Resolved _%s._%s.%s --> %s:%s' % (self.service, self.protocol, self.domain, host, port)
        return host, port

cred = X509Credentials(None, None)
creator = GreenClientCreator(reactor, LineOnlyReceiverTransport)
conn = creator.connectSRV('msrps', 'ag-projects.com',
                          connectFuncName='connectTLS', connectFuncArgs=(cred,),
                          ConnectorClass=NoisySRVConnector)

request = """MSRP 49fh AUTH
To-Path: msrps://alice@intra.example.com;tcp
From-Path: msrps://alice.example.com:9892/98cjs;tcp
-------49fh$
""".replace('\n', '\r\n')

print 'Sending:\n%s' % request
conn.write(request)
print 'Received:'
for x in conn:
    print repr(x)
    if '-------' in x:
        break
