__test__ = False


class BadDict(dict):
    def items(self):
        raise Exception()


if __name__ == '__main__':
    import threading
    test_lock = threading.RLock()
    test_lock.acquire()
    baddict = BadDict(testkey='testvalue')

    import eventlet
    eventlet.monkey_patch()

    print('pass')
