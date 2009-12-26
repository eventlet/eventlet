from eventlet import greenthread
from eventlet import coros

__all__ = ['GreenPool', 'GreenPile']
    
class GreenPool(object):
    """ The GreenPool class is a pool of green threads.
    """
    def __init__(self, size):
        self.size = size
        self.coroutines_running = set()
        self.sem = coros.Semaphore(size)
        self.no_coros_running = greenthread.Event()
            
    def resize(self, new_size):
        """ Change the max number of coroutines doing work at any given time.
    
        If resize is called when there are more than *new_size*
        coroutines already working on tasks, they will be allowed to complete 
        but no new tasks will be allowed to get launched until enough coroutines 
        finish their tasks to drop the overall quantity below *new_size*.  Until 
        then, the return value of free() will be negative.
        """
        size_delta = new_size - self.size 
        self.sem.counter += size_delta
        self.size = new_size
    
    def running(self):
        """ Returns the number of coroutines that are currently executing
        functions in the Parallel's pool."""
        return len(self.coroutines_running)

    def free(self):
        """ Returns the number of coroutines available for use."""
        return self.sem.counter

    def spawn(self, func, *args, **kwargs):
        """Run func(*args, **kwargs) in its own green thread.  Returns the
        GreenThread object that is running the function, which can be used
        to retrieve the results.
        """
        # if reentering an empty pool, don't try to wait on a coroutine freeing
        # itself -- instead, just execute in the current coroutine
        current = greenthread.getcurrent()
        if self.sem.locked() and current in self.coroutines_running:
            # a bit hacky to use the GT without switching to it
            gt = greenthread.GreenThread(current)
            gt.main(func, args, kwargs)
            return gt
        else:
            self.sem.acquire()
            gt = greenthread.spawn(func, *args, **kwargs)
            if not self.coroutines_running:
                self.no_coros_running = greenthread.Event()
            self.coroutines_running.add(gt)
            gt.link(self._spawn_done, coro=gt)
        return gt
    
    def _spawn_n_impl(self, func, args, kwargs, coro=None):
        try:
            try:
                func(*args, **kwargs)
            except (KeyboardInterrupt, SystemExit):
                raise
            except:
                # TODO in debug mode print these
                pass
        finally:
            if coro is None:
                return
            else:
                coro = greenthread.getcurrent()
                self._spawn_done(coro=coro)
    
    def spawn_n(self, func, *args, **kwargs):
        """ Create a coroutine to run func(*args, **kwargs).
        
        Returns None; the results of the function are not retrievable.
        """
        # if reentering an empty pool, don't try to wait on a coroutine freeing
        # itself -- instead, just execute in the current coroutine
        current = greenthread.getcurrent()
        if self.sem.locked() and current in self.coroutines_running:
            self._spawn_n_impl(func, args, kwargs)
        else:
            self.sem.acquire()
            g = greenthread.spawn_n(self._spawn_n_impl, func, args, kwargs, coro=True)
            if not self.coroutines_running:
                self.no_coros_running = coros.Event()
            self.coroutines_running.add(g)

    def waitall(self):
        """Waits until all coroutines in the pool are finished working."""
        self.no_coros_running.wait()
    
    def _spawn_done(self, result=None, exc=None, coro=None):
        self.sem.release()
        if coro is not None:
            self.coroutines_running.remove(coro)
        # if done processing (no more work is waiting for processing),
        # send StopIteration so that the queue knows it's done
        if self.sem.balance == self.size:
            self.no_coros_running.send(None)
            
    def waiting(self):
        """Return the number of coroutines waiting to spawn.
        """
        if self.sem.balance < 0:
            return -self.sem.balance
        else:
            return 0
                    
            
try:
    next
except NameError:
    def next(it):
        try:
            return it.next()
        except AttributeError:
            raise TypeError("%s object is not an iterator" % type(it))
        
class GreenPile(object):
    """GreenPile is an abstraction representing a bunch of I/O-related tasks.
    """
    def __init__(self, size_or_pool):
        if isinstance(size_or_pool, GreenPool):
            self.pool = size_or_pool
        else:
            self.pool = GreenPool(size_or_pool)
        self.waiters = coros.Queue()
        self.counter = 0
            
    def spawn(self, func, *args, **kw):
        """Runs *func* in its own green thread, with the result available by 
        iterating over the GreenPile object."""
        self.counter += 1
        try:
            gt = self.pool.spawn(func, *args, **kw)
            self.waiters.send(gt)
        except:
            self.counter -= 1
            raise
        
    def __iter__(self):
        return self
    
    def next(self):
        """Wait for the next result, suspending the current coroutine until it
        is available.  Raises StopIteration when there are no more results."""
        if self.counter == 0:
            raise StopIteration()
        try:
            return self.waiters.wait().wait()
        finally:
            self.counter -= 1
            
    def _do_map(self, func, iterables):
        while True:
            try:
                i = map(next, iterables)
                self.spawn(func, *i)
            except StopIteration:
                break
    
    def imap(self, function, *iterables):
        """This is the same as itertools.imap, except that *func* is 
        executed in separate green threads, with the specified concurrency 
        control.
        """
        if function is None:
            function = lambda *a: a
        # spawn first item to prime the pump
        try:
            it = map(iter, iterables)
            i = map(next, it)
            self.spawn(function, *i)
        except StopIteration:
            # if the iterable has no items, we need
            # to defer the StopIteration till someone
            # iterates over us
            self.spawn(lambda: next(iter([])))
        # spin off a coroutine to launch the rest of the items
        greenthread.spawn(self._do_map, function, it)
        return self
