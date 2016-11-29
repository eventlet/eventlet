__test__ = False


class PleaseStopUsingExceptionsAsGoto(Exception):
    pass


def fun():
    raise PleaseStopUsingExceptionsAsGoto()


if __name__ == '__main__':
    import eventlet.debug
    eventlet.debug.hub_exceptions(False)
    t = eventlet.spawn(fun)
    eventlet.sleep(0)
    try:
        t.wait()
    except PleaseStopUsingExceptionsAsGoto:
        print('pass')
