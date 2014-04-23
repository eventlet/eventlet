from __future__ import print_function
import MySQLdb as m
from eventlet import patcher
from eventlet.green import MySQLdb as gm

# no standard tests in this file, ignore
__test__ = False

if __name__ == '__main__':
    patcher.monkey_patch(all=True, MySQLdb=True)
    print("mysqltest {0}".format(",".join(sorted(patcher.already_patched.keys()))))
    print("connect {0}".format(m.connect == gm.connect))
