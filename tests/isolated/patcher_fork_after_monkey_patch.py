# Monkey patching interferes with threading in Python 3.7
# https://github.com/eventlet/eventlet/issues/592
__test__ = False


def check(n, mod, tag):
    assert len(mod._active) == n, 'Expected {} {} threads, got {}'.format(n, tag, mod._active)


if __name__ == '__main__':
    import eventlet
    import eventlet.patcher
    eventlet.monkey_patch()
    import os
    import sys
    import threading
    _threading = eventlet.patcher.original('threading')
    import eventlet.green.threading

    global threads_keep_running
    threads_keep_running = True

    def target():
        while threads_keep_running:
            eventlet.sleep(0.001)

    threads = [
        threading.Thread(target=target, name='patched'),
        _threading.Thread(target=target, name='original-1'),
        _threading.Thread(target=target, name='original-2'),
        eventlet.green.threading.Thread(target=target, name='green-1'),
        eventlet.green.threading.Thread(target=target, name='green-2'),
        eventlet.green.threading.Thread(target=target, name='green-3'),
    ]
    for t in threads:
        t.start()

    check(5, threading, 'pre-fork patched')
    check(3, _threading, 'pre-fork original')
    check(5, eventlet.green.threading, 'pre-fork green')

    pid = os.fork()
    if pid == 0:
        # Inside the child, we should only have a main _OS_ thread,
        # but green threads should survive.
        check(5, threading, 'child post-fork patched')
        check(1, _threading, 'child post-fork original')
        check(5, eventlet.green.threading, 'child post-fork green')
        threads_keep_running = False
        sys.exit()
    else:
        wait_pid, status = os.wait()
        exit_code = os.waitstatus_to_exitcode(status)
        assert wait_pid == pid
        assert exit_code == 0, exit_code

    # We're in the parent now; all threads should survive:
    check(5, threading, 'post-fork patched')
    check(3, _threading, 'post-fork original')
    check(5, eventlet.green.threading, 'post-fork green')

    threads_keep_running = False

    for t in threads:
        t.join()

    check(1, threading, 'post-join patched')
    check(1, _threading, 'post-join original')
    check(1, eventlet.green.threading, 'post-join green')
    print('pass')
