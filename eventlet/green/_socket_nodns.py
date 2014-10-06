__socket = __import__('socket')

__all__ = __socket.__all__
__patched__ = ['fromfd', 'socketpair', 'ssl', 'socket']

from eventlet.patcher import slurp_properties
slurp_properties(__socket, globals(),
                 ignore=__patched__, srckeys=dir(__socket))

os = __import__('os')
import sys
from eventlet.hubs import get_hub
from eventlet.greenio import GreenSocket as socket
from eventlet.greenio import SSL as _SSL  # for exceptions
from eventlet.greenio import _GLOBAL_DEFAULT_TIMEOUT
from eventlet.greenio import _fileobject

try:
    __original_fromfd__ = __socket.fromfd

    def fromfd(*args):
        return socket(__original_fromfd__(*args))
except AttributeError:
    pass

try:
    __original_socketpair__ = __socket.socketpair

    def socketpair(*args):
        one, two = __original_socketpair__(*args)
        return socket(one), socket(two)
except AttributeError:
    pass


def _convert_to_sslerror(ex):
    """ Transliterates SSL.SysCallErrors to socket.sslerrors"""
    return sslerror((ex.args[0], ex.args[1]))


class GreenSSLObject(object):
    """ Wrapper object around the SSLObjects returned by socket.ssl, which have a
    slightly different interface from SSL.Connection objects. """

    def __init__(self, green_ssl_obj):
        """ Should only be called by a 'green' socket.ssl """
        self.connection = green_ssl_obj
        try:
            # if it's already connected, do the handshake
            self.connection.getpeername()
        except:
            pass
        else:
            try:
                self.connection.do_handshake()
            except _SSL.SysCallError as e:
                raise _convert_to_sslerror(e)

    def read(self, n=1024):
        """If n is provided, read n bytes from the SSL connection, otherwise read
        until EOF. The return value is a string of the bytes read."""
        try:
            return self.connection.read(n)
        except _SSL.ZeroReturnError:
            return ''
        except _SSL.SysCallError as e:
            raise _convert_to_sslerror(e)

    def write(self, s):
        """Writes the string s to the on the object's SSL connection.
        The return value is the number of bytes written. """
        try:
            return self.connection.write(s)
        except _SSL.SysCallError as e:
            raise _convert_to_sslerror(e)

    def server(self):
        """ Returns a string describing the server's certificate. Useful for debugging
        purposes; do not parse the content of this string because its format can't be
        parsed unambiguously. """
        return str(self.connection.get_peer_certificate().get_subject())

    def issuer(self):
        """Returns a string describing the issuer of the server's certificate. Useful
        for debugging purposes; do not parse the content of this string because its
        format can't be parsed unambiguously."""
        return str(self.connection.get_peer_certificate().get_issuer())
