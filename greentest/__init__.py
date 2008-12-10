# package is named greentest, not test, so it won't be confused with test in stdlib
import sys

disabled_marker = '-*-*-*-*-*- disabled -*-*-*-*-*-'
def exit_disabled():
    sys.exit(disabled_marker)

def exit_unless_twisted():
    from eventlet.api import get_hub
    if 'Twisted' not in type(get_hub()).__name__:
        exit_disabled()


