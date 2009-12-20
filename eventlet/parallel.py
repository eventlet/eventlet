from eventlet.coros import Semaphore, Queue
from eventlet.api import spawn, getcurrent
import sys

__all__ = ['Parallel']
    
class Parallel(object):
    """ The Parallel class allows you to easily control coroutine concurrency.
    """
    def __init__(self, max_size):
        self.max_size = max_size
        self.coroutines_running = set()
        self.sem = Semaphore(max_size)
        self._results = Queue()
    
    def resize(self, new_max_size):
        """ Change the max number of coroutines doing work at any given time.
    
        If resize is called when there are more than *new_max_size*
        coroutines already working on tasks, they will be allowed to complete but no 
        new tasks will be allowed to get launched until enough coroutines finish their
        tasks to drop the overall quantity below *new_max_size*.  Until then, the 
        return value of free() will be negative.
        """
        max_size_delta = new_max_size - self.max_size 
        self.sem.counter += max_size_delta
        self.max_size = new_max_size
    
    @property
    def current_size(self):
        """ The current size is the number of coroutines that are currently 
        executing functions in the Parallel's pool."""
        return len(self.coroutines_running)

    def free(self):
        """ Returns the number of coroutines available for use."""
        return self.sem.counter

    def _coro_done(self, coro, result, exc=None):
        self.sem.release()
        self.coroutines_running.remove(coro)
        self._results.send(result)
        # if done processing (no more work is being done),
        # send StopIteration so that the queue knows it's done
        if self.sem.balance == self.max_size:
            self._results.send_exception(StopIteration)
                        
    def spawn(self, func, *args, **kwargs):
        """ Create a coroutine to run func(*args, **kwargs).  Returns a 
        Coro object that can be used to retrieve the results of the function.
        """
        # if reentering an empty pool, don't try to wait on a coroutine freeing
        # itself -- instead, just execute in the current coroutine
        current = getcurrent()
        if self.sem.locked() and current in self.coroutines_running:
            func(*args, **kwargs)
        else:
            self.sem.acquire()
            p = spawn(func, *args, **kwargs)
            self.coroutines_running.add(p)
            p.link(self._coro_done)

        return p
                
    def wait(self):
        """Wait for the next execute in the pool to complete,
        and return the result."""
        return self.results.wait()
        
    def results(self):
        """ Returns an iterator over the results from the worker coroutines."""
        return self._results
        
    def _do_spawn_all(self, func, iterable):
        for i in iterable:
            if not isinstance(i, tuple):
                self.spawn(func, i)
            else:
                self.spawn(func, *i)
    
    def spawn_all(self, func, iterable):
        """ Applies *func* over every item in *iterable* using the concurrency 
        present in the pool.  This function is a generator which yields the 
        results of *func* as applied to the members of the iterable."""
        
        spawn(self._do_spawn_all, func, iterable)
        return self.results()