from nose.plugins.skip import SkipTest


def test_greendns_getnameinfo_resolve_port():
    try:
        from eventlet.support import greendns
    except ImportError:
        raise SkipTest('greendns requires package dnspython')

    # https://bitbucket.org/eventlet/eventlet/issue/152
    _, port1 = greendns.getnameinfo(('127.0.0.1', 80), 0)
    _, port2 = greendns.getnameinfo(('localhost', 80), 0)
    assert port1 == port2 == 'http'
