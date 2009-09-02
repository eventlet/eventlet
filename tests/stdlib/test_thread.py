from eventlet.green import thread
from eventlet.green import time

# necessary to initialize the hub before running on 2.5
from eventlet import api
api.get_hub()

# in Python < 2.5, the import does all the testing,
# so we have to wrap that in test_main as well
def test_main():
    import sys
    sys.modules['thread'] = thread
    sys.modules['time'] = time
    from test import test_thread
    if hasattr(test_thread, 'test_main'):
        # > 2.6
        test_thread.test_main()

if __name__ == "__main__":
    test_main()