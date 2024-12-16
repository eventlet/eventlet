import queue
import threading


class Worker(threading.Thread):
    EXIT_SENTINEL = object()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.q = queue.Queue(maxsize=-1)
        self.daemon = True

    def run(self):
        while True:
            task = self.q.get()
            if task == self.EXIT_SENTINEL:
                break
            print(f"Treating task {task}")
            # Pretend to work

    def submit(self, job):
        self.q.put(job)

    def terminate(self):
        self.q.put(self.EXIT_SENTINEL)
        self.join()


if __name__ == "__main__":
    import eventlet
    eventlet.patcher.monkey_patch()

    worker = Worker()
    assert not worker.is_alive()
    worker.start()
    assert worker.is_alive()
    worker.submit(1)
    worker.terminate()
    assert not worker.is_alive()
    print("pass")
