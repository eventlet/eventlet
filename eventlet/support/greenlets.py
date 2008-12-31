
try:
    import greenlet
    getcurrent = greenlet.getcurrent
    GreenletExit = greenlet.GreenletExit
    greenlet = greenlet.greenlet
except ImportError, e:
    try:
        from py.magic import greenlet
        getcurrent = greenlet.getcurrent
        GreenletExit = greenlet.GreenletExit
    except ImportError:
        try:
            from stackless import greenlet
            getcurrent = greenlet.getcurrent
            GreenletExit = greenlet.GreenletExit
        except ImportError:
            try:
                from support.stacklesss import greenlet, getcurrent, GreenletExit
            except ImportError, e:
                raise ImportError("Unable to find an implementation of greenlet.")
