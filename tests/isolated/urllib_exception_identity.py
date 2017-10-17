__test__ = False

if __name__ == '__main__':
    import sys
    if sys.version_info[0] == 2:
        import urllib2 as original
        from eventlet.green import urllib2 as green
    elif sys.version_info[0] == 3:
        from urllib import error as original
        from eventlet.green.urllib import error as green
    else:
        raise Exception

    cases = (
        'URLError',
        'HTTPError',
        'ContentTooShortError',
    )
    for c in cases:
        if hasattr(original, c):
            assert getattr(green, c) is getattr(original, c), c
    print('pass')
