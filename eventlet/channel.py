from eventlet import coros

class channel(coros.Channel):

    def receive(self):
        return self.wait()

    @property
    def balance(self):
        return len(self.items) - len(self._waiters)

import warnings
warnings.warn("channel.py is deprecated by coros.Channel", DeprecationWarning, stacklevel=2)

if __name__ == '__main__':
    from eventlet import proc, api
    c = channel()
    proc.spawn(c.send, 'X')
    proc.spawn(c.send, 'Y')
    assert c.wait() == 'X', c
    assert c.wait() == 'Y', c
    assert api.with_timeout(1, c.wait, timeout_value='hello') == 'hello', c

