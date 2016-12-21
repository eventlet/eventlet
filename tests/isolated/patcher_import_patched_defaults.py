import os
__test__ = False


if os.environ.get('eventlet_test_import_patched_defaults') == '1':
    try:
        import urllib.request as target
    except ImportError:
        import urllib as target
    t = target.socket.socket
    import eventlet.green.socket
    if issubclass(t, eventlet.green.socket.socket):
        print('pass')
    else:
        print('Fail. Target socket not green: {0} bases {1}'.format(t, t.__bases__))
