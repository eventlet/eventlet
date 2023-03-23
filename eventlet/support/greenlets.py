import packaging.version

import greenlet
getcurrent = greenlet.greenlet.getcurrent
GreenletExit = greenlet.greenlet.GreenletExit
preserves_excinfo = (packaging.version.parse(greenlet.__version__)
                     >= packaging.version.parse('0.3.2'))
greenlet = greenlet.greenlet
