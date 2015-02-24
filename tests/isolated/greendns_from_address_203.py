__test__ = False


def main():
    import eventlet
    try:
        from dns import reversename
    except ImportError:
        print('skip:require dns (package dnspython)')
        return
    eventlet.monkey_patch(all=True)
    reversename.from_address('127.0.0.1')
    print('pass')

if __name__ == '__main__':
    main()
