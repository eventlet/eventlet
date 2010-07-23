from eventlet import patcher
from eventlet.green import asyncore
from eventlet.green import select
from eventlet.green import socket
from eventlet.green import threading
from eventlet.green import time

patcher.inject("test.test_asyncore", globals())

def new_closeall_check(self, usedefault):
    # Check that close_all() closes everything in a given map

    l = []
    testmap = {}
    for i in range(10):
        c = dummychannel()
        l.append(c)
        self.assertEqual(c.socket.closed, False)
        testmap[i] = c

    if usedefault:
        # the only change we make is to not assign to asyncore.socket_map
        # because doing so fails to assign to the real asyncore's socket_map
        # and thus the test fails
        socketmap = asyncore.socket_map.copy()
        try:
            asyncore.socket_map.clear()
            asyncore.socket_map.update(testmap)
            asyncore.close_all()
        finally:
            testmap = asyncore.socket_map.copy()
            asyncore.socket_map.clear()
            asyncore.socket_map.update(socketmap)
    else:
        asyncore.close_all(testmap)

    self.assertEqual(len(testmap), 0)

    for c in l:
        self.assertEqual(c.socket.closed, True)
        
HelperFunctionTests.closeall_check = new_closeall_check

# Eventlet's select() emulation doesn't support the POLLPRI flag,
# which this test relies on.  Therefore, nuke it!
BaseTestAPI.test_handle_expt = lambda *a, **kw: None

if __name__ == "__main__":
    test_main()
