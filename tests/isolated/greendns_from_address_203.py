__test__ = False

if __name__ == '__main__':
    import sys
    import eventlet
    try:
        from dns import reversename
    except ImportError:
        print('skip:require dns (package dnspython)')
        sys.exit(1)
    eventlet.monkey_patch(all=True)
    reversename.from_address('127.0.0.1')
    print('pass')
