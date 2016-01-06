if __name__ == '__main__':
    import eventlet
    eventlet.monkey_patch()

    # Leaving unpatched select methods in the select module is a recipe
    # for trouble and this test makes sure we don't do that.
    #
    # Issues:
    # * https://bitbucket.org/eventlet/eventlet/issues/167
    # * https://github.com/eventlet/eventlet/issues/169
    import select
    for name in ['poll', 'epoll', 'kqueue', 'kevent']:
        assert not hasattr(select, name), name

    print('pass')
