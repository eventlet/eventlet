if __name__ == '__main__':
    import eventlet
    from eventlet.greenthread import sleep, spawn

    eventlet.monkey_patch()

    import signal
    import os

    thread = None
    timed_out = False

    def on_timeout(signum, frame):
        global timed_out
        timed_out = True
        thread.kill()

    def blocking_read(fd):
        os.read(fd, 4096)

    signal.signal(signal.SIGALRM, on_timeout)
    signal.alarm(3)

    read_fd, write_fd = os.pipe()
    thread = spawn(blocking_read, read_fd)
    sleep(0)

    assert not timed_out

    print('pass')
