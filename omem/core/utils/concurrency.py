"""Concurrency utilities for OMem."""

import threading


class RWLock:
    """A standard Reader-Writer lock.
    Allows multiple concurrent readers, but mutually exclusive writers.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._read_ready = threading.Condition(self._lock)
        self._readers = 0
        self._writers = 0

    def acquire_read(self):
        self._lock.acquire()
        while self._writers > 0:
            self._read_ready.wait()
        self._readers += 1
        self._lock.release()

    def release_read(self):
        self._lock.acquire()
        self._readers -= 1
        if self._readers == 0:
            self._read_ready.notify_all()
        self._lock.release()

    def acquire_write(self):
        self._lock.acquire()
        while self._writers > 0 or self._readers > 0:
            self._read_ready.wait()
        self._writers += 1
        self._lock.release()

    def release_write(self):
        self._lock.acquire()
        self._writers -= 1
        self._read_ready.notify_all()
        self._lock.release()


class ReadContext:
    def __init__(self, lock: RWLock):
        self.lock = lock

    def __enter__(self):
        self.lock.acquire_read()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release_read()


class WriteContext:
    def __init__(self, lock: RWLock):
        self.lock = lock

    def __enter__(self):
        self.lock.acquire_write()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release_write()
