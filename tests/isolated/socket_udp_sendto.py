# Stary by monkey patching
import eventlet.patcher
eventlet.monkey_patch()

import contextlib
import socket
import sys
PY3 = (sys.version_info >= (3,))
queue = eventlet.patcher.original('queue' if PY3 else 'Queue')
threading = eventlet.patcher.original('threading')


class UDPServer(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.running = threading.Event()
        self.queue = queue.Queue()

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        with contextlib.closing(sock):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            self.port = 0

            server_addr = ('127.0.0.1', 0)
            sock.bind(server_addr)
            port = sock.getsockname()[1]
            self.address = (server_addr[0], port)
            self.running.set()

            data, client_addr = sock.recvfrom(1024)
            self.queue.put(data)

            data, client_addr = sock.recvfrom(1024)
            self.queue.put(data)


def main():
    server = UDPServer()
    server.start()
    server.running.wait()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    msg1 = b'message1\n'
    sock.sendto(msg1, server.address)
    received = server.queue.get()
    if received != msg1:
        raise Exception("sent %r, received %r" % (msg1, received))

    msg2 = b'message1\n'
    sock.sendto(msg2, 0, server.address)
    received = server.queue.get()
    if received != msg2:
        raise Exception("sent %r, received %r" % (msg2, received))

    server.join()

    print("pass")


if __name__ == "__main__":
    main()
