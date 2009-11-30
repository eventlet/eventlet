""" Convenience module for running standard library tests with nose.  The standard tests are not especially homogeneous, but they mostly expose a test_main method that does the work of selecting which tests to run based on what is supported by the platform.  On its own, Nose would run all possible tests and many would fail; therefore we collect all of the test_main methods here in one module and Nose can run it.  Hopefully in the future the standard tests get rewritten to be more self-contained.

Many of these tests make connections to external servers, causing failures when run while disconnected from the internet.
"""


def import_main(g, name):
    try:
        modobj = __import__(name, g, fromlist=['test_main'])
    except ImportError:
        print "Not importing %s, it doesn't exist in this installation/version of Python" % name
        return
    else:
        method_name = name + "_test_main"
        try:
            g[method_name] = modobj.test_main
            modobj.test_main.__name__ = name + '.test_main'
        except AttributeError:
            print "No test_main for %s, assuming it tests on import" % name

import_main(globals(), 'test_SimpleHTTPServer')
import_main(globals(), 'test_asynchat')
import_main(globals(), 'test_asyncore')
import_main(globals(), 'test_ftplib')
import_main(globals(), 'test_httplib')
#import_main(globals(), 'test_httpservers')
import_main(globals(), 'test_select')
import_main(globals(), 'test_socket')
#import_main(globals(), 'test_socket_ssl')
import_main(globals(), 'test_socketserver')
#import_main(globals(), 'test_ssl')
import_main(globals(), 'test_thread')
#import_main(globals(), 'test_threading')
#import_main(globals(), 'test_threading_local')
import_main(globals(), 'test_timeout')
import_main(globals(), 'test_urllib')
#import_main(globals(), 'test_urllib2')
#import_main(globals(), 'test_urllib2_localnet')