# no standard tests in this file, ignore
__test__ = False

if __name__ == '__main__':
    import os
    import eventlet
    server = eventlet.listen(('localhost', 12345))
    t = eventlet.Timeout(0.01)
    try:
        new_sock, address = server.accept()
    except eventlet.Timeout as t:
        pass

    pid = os.fork()
    if not pid:
        t = eventlet.Timeout(0.1)
        try:
            new_sock, address = server.accept()
        except eventlet.Timeout as t:
            print("accept blocked")
    else:
        kpid, status = os.wait()
        assert kpid == pid
        assert status == 0
        print("child died ok")
