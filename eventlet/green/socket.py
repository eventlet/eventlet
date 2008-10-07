from __future__ import absolute_import
from socket import _fileobject, fromfd as __fromfd, socketpair as __socketpair
from socket import *

from eventlet.greenio import GreenSocket as socket, GreenSSL as _GreenSSL
from eventlet.twisteds.util import block_on as _block_on

def fromfd(*args):
    return socket(__fromfd(*args))

def gethostbyname(name):
    from twisted.internet import reactor
    return _block_on(reactor.resolve(name))

# XXX there're few more blocking functions in socket

def socketpair(family=None, type=SOCK_STREAM, proto=0):
    if family is None:
        try:
            family = AF_UNIX
        except AttributeError:
            family = AF_INET

    a, b = __socketpair(family, type, proto)
    return socket(a), socket(b)

def ssl(sock, certificate=None, private_key=None):
    from OpenSSL import SSL
    context = SSL.Context(SSL.SSLv23_METHOD)
    if certificate is not None:
        context.use_certificate_file(certificate)
    if private_key is not None:
        context.use_privatekey_file(private_key)
    context.set_verify(SSL.VERIFY_NONE, lambda *x: True)

    ## TODO only do this on client sockets? how?
    connection = SSL.Connection(context, sock)
    connection.set_connect_state()
    return _GreenSSL(connection)
