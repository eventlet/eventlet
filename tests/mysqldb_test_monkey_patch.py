from __future__ import print_function
from eventlet import patcher

# no standard tests in this file, ignore
__test__ = False

if __name__ == '__main__':
    import MySQLdb as m
    from eventlet.green import MySQLdb as gm
    patcher.monkey_patch(all=True, MySQLdb=True)
    print("mysqltest {0}".format(",".join(sorted(patcher.already_patched.keys()))))
    print("connect {0}".format(m.connect == gm.connect))
