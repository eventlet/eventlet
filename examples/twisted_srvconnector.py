from twisted.internet import reactor
from twisted.names.srvconnect import SRVConnector
from gnutls.interfaces.twisted import X509Credentials

from eventlet.twistedutil.protocol import GreenClientCreator
from eventlet.twistedutil.protocols.basic import LineOnlyReceiverTransport

class NoisySRVConnector(SRVConnector):

    def _ebGotServers(self, failure):
        #self.failure = failure
        return SRVConnector._ebGotServers(self, failure)

    def pickServer(self):
        host, port = SRVConnector.pickServer(self)
        #if not isinstance(port, int) and self.failure:
        #        self.failure.raiseException()
        print 'Resolved _%s._%s.%s --> %s:%s' % (self.service, self.protocol, self.domain, host, port)
        return host, port

# why TypeError is not raised here?

cred = X509Credentials(None, None)
creator = GreenClientCreator(reactor, LineOnlyReceiverTransport)
conn = creator.connectSRV('msrpsx', 'ag-projects.com',
                          connectFuncName='connectTLS', connectFuncArgs=(cred,),
                          ConnectorClass=NoisySRVConnector)

request = """MSRP 49fh AUTH
To-Path: msrps://alice@intra.example.com;tcp
From-Path: msrps://alice.example.com:9892/98cjs;tcp
-------49fh$
""".replace('\n', '\r\n')

conn.write(request)
for x in conn:
    print x
    if '-------' in x:
        break
