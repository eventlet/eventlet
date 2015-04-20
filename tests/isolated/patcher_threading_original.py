import sys
import threading


# no standard tests in this file, ignore
__test__ = False


class ImportEventlet(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.same_module = None

    def run(self):
        # https://github.com/eventlet/eventlet/issues/230
        # Test importing eventlet for the first time in a thread:
        # eventlet.patcher.original() must not reload threading.py twice.
        mod1 = sys.modules['threading']
        import eventlet.patcher
        mod2 = eventlet.patcher.original('threading')
        self.same_module = mod2 is mod1


if __name__ == '__main__':
    thread = ImportEventlet()
    thread.start()
    thread.join()
    if thread.same_module:
        print("pass")
    else:
        print("failed")
