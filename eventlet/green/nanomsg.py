# coding: utf-8
"""The :mod:`nanomsg` module wraps the :class:`Socket`
found in :mod:`nanomsg-python <nanomsg>` to be non blocking.
"""

__nanomsg__ = __import__('nanomsg')
from eventlet.patcher import slurp_properties
from eventlet.hubs import trampoline
from nanomsg import wrapper

__nanomsg__.__all__ = ['wrapper', 'NanoMsgError', 'NanoMsgAPIError', 'Device', 'Socket']

for name, value in wrapper.nn_symbols():
    if name.startswith('NN_'):
        name = name[3:]
    __nanomsg__.__all__.append(name)

__patched__ = ['Socket']
slurp_properties(__nanomsg__, globals(), ignore=__patched__)


class Socket(__nanomsg__.Socket):

    def recv(self, buf=None, flags=0):
        """Recieve a message."""

        # Wait for the receive file descriptor using eventlet
        while True:

            # Call the eventlent hub trampoline function to wait for a notification on the
            # receive file descriptor.
            trampoline(self.recv_fd, read=True)

            # Don't allow nn_recv() to block
            flags = flags | __nanomsg__.DONTWAIT

            if buf is None:
                rtn, out_buf = wrapper.nn_recv(self.fd, flags)
            else:
                rtn, out_buf = wrapper.nn_recv(self.fd, buf, flags)

            # Return if we received a valid message
            if(rtn > 0):
                return bytes(memoryview(out_buf))[:rtn]

    def send(self, msg, flags=0):
        """Send a message"""

        while True:
            trampoline(self.send_fd, write=True)
            ret = wrapper.nn_send(self.fd, msg, flags | __nanomsg__.DONTWAIT)
            if(ret > 0):
                break

    def poll(in_sockets, out_sockets, timeout=-1):
        raise NotImplementedError("poll is not implemented in the nanomsg eventlet wrapper")
