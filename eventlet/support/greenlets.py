import distutils.version

try:
    import greenlet
    getcurrent = greenlet.greenlet.getcurrent
    GreenletExit = greenlet.greenlet.GreenletExit
    preserves_excinfo = (distutils.version.LooseVersion(greenlet.__version__)
            >= distutils.version.LooseVersion('0.3.2'))
    greenlet = greenlet.greenlet
except ImportError, e:
    raise
    try:
        from py.magic import greenlet
        getcurrent = greenlet.getcurrent
        GreenletExit = greenlet.GreenletExit
        preserves_excinfo = False
    except ImportError:
        try:
            from stackless import greenlet
            getcurrent = greenlet.getcurrent
            GreenletExit = greenlet.GreenletExit
            preserves_excinfo = False
        except ImportError:
            try:
                from support.stacklesss import greenlet, getcurrent, GreenletExit
                preserves_excinfo = False
                (greenlet, getcurrent, GreenletExit) # silence pyflakes
            except ImportError, e:
                raise ImportError("Unable to find an implementation of greenlet.")
