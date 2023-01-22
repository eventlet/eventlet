# coding: utf-8
"""The :mod:`nanomsg` module wraps the :class:`Socket`
found in :mod:`nanomsg-python <nanomsg>` to be non blocking.
"""

__nanomsg__ = __import__('nanomsg')
from eventlet.patcher import slurp_properties
from eventlet.hubs import trampoline
from errno import EAGAIN

if not hasattr(__nanomsg__, "__all__"):
    __nanomsg__.__all__ = ['wrapper', 'NanoMsgError', 'NanoMsgAPIError', 'Device', 'Socket']

for name, value in __nanomsg__.wrapper.nn_symbols():
    if name.startswith('NN_'):
        name = name[3:]
    __nanomsg__.__all__.append(name)

__patched__ = ['Socket']
slurp_properties(__nanomsg__, globals(), ignore=__patched__)


class Socket(__nanomsg__.Socket):

    def recv(self, buf=None, flags=0):
        """Recieve a message."""

        flags |= __nanomsg__.DONTWAIT

        while True:
            if buf is None:
                rtn, out_buf = __nanomsg__.wrapper.nn_recv(self.fd, flags)
            else:
                rtn, out_buf = __nanomsg__.wrapper.nn_recv(self.fd, buf, flags)

            if rtn < 0:
                if __nanomsg__.wrapper.nn_errno() == EAGAIN:
                    trampoline(self.recv_fd, read=True)
            elif rtn >= 0:
                return bytes(memoryview(out_buf))[:rtn]
            else:
                raise __nanomsg__.NanoMsgAPIError()

    def send(self, msg, flags=0):
        """Send a message"""

        flags |= __nanomsg__.DONTWAIT

        while True:
            ret = __nanomsg__.wrapper.nn_send(self.fd, msg, flags)
            if ret >= 0:
                return ret
            if __nanomsg__.wrapper.nn_errno() == EAGAIN:
                trampoline(self.send_fd, write=True)
                continue
            raise __nanomsg__.NanoMsgAPIError()

    def poll(in_sockets, out_sockets, timeout=-1):
        raise NotImplementedError("poll is not implemented in the nanomsg eventlet wrapper")
