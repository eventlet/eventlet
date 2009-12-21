from eventlet.coros import Semaphore, Queue, Event
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
        self.no_coros_running = Event()
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

    def spawn(self, func, *args, **kwargs):
        """Run func(*args, **kwargs) in its own green thread.
        """
        return self._spawn(False, func, *args, **kwargs)
        
    def spawn_q(self, func, *args, **kwargs):
        """Run func(*args, **kwargs) in its own green thread.
        
        The results of func are stuck in the results() iterator.
        """
        self._spawn(True, func, *args, **kwargs)
        
    def spawn_n(self, func, *args, **kwargs):
        """ Create a coroutine to run func(*args, **kwargs).
        
        Returns None; the results of the function are not retrievable.  
        The results of the function are not put into the results() iterator.
        """
        self._spawn(False, func, *args, **kwargs)

    def _spawn(self, send_result, func, *args, **kwargs):
        # if reentering an empty pool, don't try to wait on a coroutine freeing
        # itself -- instead, just execute in the current coroutine
        current = getcurrent()
        if self.sem.locked() and current in self.coroutines_running:
            func(*args, **kwargs)
        else:
            self.sem.acquire()
            p = spawn(func, *args, **kwargs)
            if not self.coroutines_running:
                self.no_coros_running = Event()
            self.coroutines_running.add(p)
            p.link(self._spawn_done, send_result=send_result, coro=p)
        return p

    def waitall(self):
        """Waits until all coroutines in the pool are finished working."""
        self.no_coros_running.wait()
    
    def _spawn_done(self, result=None, exc=None, send_result=False, coro=None):
        self.sem.release()
        self.coroutines_running.remove(coro)
        if send_result:
            self._results.send(result)
        # if done processing (no more work is waiting for processing),
        # send StopIteration so that the queue knows it's done
        if self.sem.balance == self.max_size:
            if send_result:
                self._results.send_exception(StopIteration)
            self.no_coros_running.send(None)            

    def wait(self):
        """Wait for the next execute in the pool to complete,
        and return the result."""
        return self.results.wait()
        
    def results(self):
        """ Returns an iterator over the results from the worker coroutines."""
        return self._results
        
    def _do_spawn_all(self, func, iterable):
        for i in iterable:
            # if the list is composed of single arguments, use those
            if not isinstance(i, (tuple, list)):
                self.spawn_q(func, i)
            else:
                self.spawn_q(func, *i)
    
    def spawn_all(self, func, iterable):
        """ Applies *func* over every item in *iterable* using the concurrency 
        present in the pool.  This function is a generator which yields the 
        results of *func* as applied to the members of the iterable."""
        
        spawn(self._do_spawn_all, func, iterable)
        return self.results()