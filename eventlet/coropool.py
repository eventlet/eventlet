# replacement of CoroutinePool implemented with proc module
from eventlet import coros, proc, api

class Pool(object):

    def __init__(self, min_size=0, max_size=4):
        if min_size > max_size:
            raise ValueError('min_size cannot be bigger than max_size')
        self.sem = coros.Semaphore(max_size)
        for _ in xrange(min_size):
            self.sem.acquire()
        self.procs = proc.RunningProcSet()

    def free(self):
        return self.sem.counter

    def execute(self, func, *args, **kwargs):
        """Execute func in one of the coroutines maintained
        by the pool, when one is free.

        Immediately returns a Proc object which can be queried
        for the func's result.

        >>> pool = Pool()
        >>> task = p.execute(lambda a: ('foo', a), 1)
        >>> task.wait()
        ('foo', 1)
        """
        # if reentering an empty pool, don't try to wait on a coroutine freeing
        # itself -- instead, just execute in the current coroutine
        if self.sem.locked() and api.getcurrent() in self.procs:
            p = proc.spawn(func, *args, **kwargs)
            try:
                p.wait()
            except:
                pass
        else:
            self.sem.acquire()
            p = self.procs.spawn(func, *args, **kwargs)
            p.link(lambda p: self.sem.release())
        return p

    execute_async = execute

    def waitall(self):
        return self.procs.waitall()

    wait_all = waitall

    def killall(self):
        return self.procs.killall()

 
