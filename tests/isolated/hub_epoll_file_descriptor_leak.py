__test__ = False

if __name__ == '__main__':

    import eventlet
    from eventlet import hubs
    import eventlet.hubs
    import threading
    import os
    import gc

    rfd, wfd = os.pipe()
    reader = eventlet.greenio.py3.GreenPipe(rfd, "rb", buffering=2)

    def epoll_count():
        epoll_count = 0
        for f in os.listdir("/proc/self/fd"):
            try:
                p = os.path.join("/proc/self/fd", f)
                if os.readlink(p) == "anon_inode:[eventpoll]":
                    epoll_count += 1
            except:
                pass
        return epoll_count

    def fun(fd):
        # separate trampoline may trigger additional bugs with multiple
        # listeners
        hubs.trampoline(fd, write=True)

        with eventlet.greenio.py3.GreenPipe(fd, "wb", buffering=0) as w:
            w.write(b"12")


        # it would be wasteful to drop and recreate hub state every time
        # all listeners stop
        epolls = epoll_count()
        assert epolls == 2, ('epoll file descriptor closed while it might '
            'still be used. Currently having {}'.format(epolls))

        hubs._threadlocal.hub.abort(wait=True)

        # this makes it work
        #hubs._threadlocal.hub.__del__()
        # this one does not help
        #del hubs._threadlocal.hub

    t = threading.Thread(target=fun, args=(wfd,))
    t.start()

    assert reader.read(2) == b"12"
    reader.close()

    t.join()

    # we need to ignore one FD here, since that is the one of the current
    # thread (which is fine to exist)
    epolls = epoll_count()
    assert epolls == 1, '{} epoll file descriptor leaked'.format(
        epolls - 1)

    print('pass')
