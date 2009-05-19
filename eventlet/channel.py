from eventlet import coros

class channel(coros.queue):

    def __init__(self):
        coros.queue.__init__(self, 0)

    def receive(self):
        return self.wait()

    @property
    def balance(self):
        return self.sem.balance


