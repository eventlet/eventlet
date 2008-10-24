from twisted.internet import pollreactor; pollreactor.install()
from twisted.internet.protocol import Factory
from twisted.internet import reactor
from twisted.protocols import basic

from xcaplib.client import XCAPClient

from eventlet.api import get_hub
from eventlet.twisteds.util import callInGreenThread


class LineOnlyReceiver(basic.LineOnlyReceiver):

    def lineReceived(self, line):
        print 'received: %r' % line
        if not line:
            return
        app, context, node = (line + ' ').split(' ', 3) 
        context = {'u' : 'users', 'g': 'global'}.get(context, context)
        d = callInGreenThread(client._get, app, node, globaltree=context=='global')
        def callback(result):
            self.transport.write(str(result))
        def errback(error):
            self.transport.write(error.getTraceback())
        d.addCallback(callback)
        d.addErrback(errback)

class MyFactory(Factory):
    protocol = LineOnlyReceiver

def xcaplib_enable_eventlet():
    from eventlet.green import urllib2
    from xcaplib import httpclient
    # replacing all the references to the old urllib2 in xcaplib:
    httpclient.urllib2 = urllib2
    httpclient.HTTPRequest.__bases__ = (urllib2.Request,)

xcaplib_enable_eventlet()
client = XCAPClient('https://xcap.sipthor.net/xcap-root', 'alice@example.com', '123')
reactor.listenTCP(8007, MyFactory())
get_hub().switch()

