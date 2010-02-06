""" Convenience module for running standard library tests with nose.  The standard tests are not especially homogeneous, but they mostly expose a test_main method that does the work of selecting which tests to run based on what is supported by the platform.  On its own, Nose would run all possible tests and many would fail; therefore we collect all of the test_main methods here in one module and Nose can run it.  Hopefully in the future the standard tests get rewritten to be more nosey.

Many of these tests make connections to external servers, and all.py tries to skip these tests rather than failing them, so you can get some work done on a plane.
"""


def import_main(name):
    try:
        modobj = __import__(name, globals(), locals(), ['test_main'])
    except ImportError:
        print "Not importing %s, it doesn't exist in this installation/version of Python" % name
        return
    else:
        method_name = name + "_test_main"
        try:
            globals()[method_name] = modobj.test_main
            modobj.test_main.__name__ = name + '.test_main'
        except AttributeError:
            print "No test_main for %s, assuming it tests on import" % name
            
    
# quick and dirty way of testing whether we can access
# remote hosts; any tests that try internet connections
# will fail if we cannot
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.settimeout(0.5)
    s.connect(('eventlet.net', 80))
    s.close()
    have_network_access = True
except socket.error, e:
    print "Skipping network tests"
    have_network_access = False
    
import_main('test_select')
import_main('test_SimpleHTTPServer')
import_main('test_asynchat')
import_main('test_asyncore')
import_main('test_ftplib')
import_main('test_httplib')
if have_network_access:
    import_main('test_httpservers')
import_main('test_os')
import_main('test_queue')
if have_network_access:
    import_main('test_socket')
import_main('test_socket_ssl')
#import_main('test_socketserver')
#import_main('test_subprocess')
if have_network_access:
    import_main('test_ssl')
import_main('test_thread')
#import_main('test_threading')
import_main('test_threading_local')
if have_network_access:
    import_main('test_timeout')
import_main('test_urllib')
if have_network_access:
    import_main('test_urllib2')
import_main('test_urllib2_localnet')
