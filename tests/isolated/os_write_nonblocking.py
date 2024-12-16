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

    def blocking_write(fd):
        # once the write buffer is filled up, it should go to sleep instead of blocking
        # write 1 byte at a time as writing large data will block
        # even if select/poll claims otherwise
        for i in range(1, 1000000):
            os.write(fd, b'\0')

    signal.signal(signal.SIGALRM, on_timeout)
    signal.alarm(5)

    read_fd, write_fd = os.pipe()
    thread = spawn(blocking_write, write_fd)
    # 2 secs is enough time for write buffer to fill up
    sleep(2)

    assert not timed_out

    print('pass')
