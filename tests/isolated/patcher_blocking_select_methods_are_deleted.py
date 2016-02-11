__test__ = False

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
    # FIXME: must also delete `poll`, but it breaks subprocess `communicate()`
    # https://github.com/eventlet/eventlet/issues/290
    for name in ['devpoll', 'epoll', 'kqueue', 'kevent']:
        assert not hasattr(select, name), name

    import sys

    if sys.version_info >= (3, 4):
        import selectors
        for name in [
            'PollSelector',
            'EpollSelector',
            'DevpollSelector',
            'KqueueSelector',
        ]:
            assert not hasattr(selectors, name), name

        default = selectors.DefaultSelector
        assert default is selectors.SelectSelector, default

    print('pass')
