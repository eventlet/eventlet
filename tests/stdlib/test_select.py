from eventlet import api
api.sleep(0)  # initialize the hub
from eventlet.green import select
import sys
sys.modules['select'] = select

from test.test_select import *

if __name__ == "__main__":
    try:
        test_main()
    except NameError:
        pass # 2.5