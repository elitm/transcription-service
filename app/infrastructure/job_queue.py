"""In-memory thread-safe job queue with maximum depth."""
from typing import Optional
from queue import Queue
import threading


class QueueFullError(Exception):
    pass


class JobQueue:
    def __init__(self, max_depth: int = 5):
        self.max_depth = max_depth
        self._queue: Queue[str] = Queue(maxsize=0)
        self._lock = threading.RLock()
        self._size = 0

    def enqueue(self, job_id: str) -> None:
        with self._lock:
            if self.is_full():
                raise QueueFullError(f"Queue is full (max {self.max_depth})")
            self._queue.put(job_id)
            self._size += 1

    def dequeue(self) -> Optional[str]:
        with self._lock:
            if self._size == 0:
                return None
            job_id = self._queue.get_nowait()
            self._size -= 1
            return job_id

    def size(self) -> int:
        with self._lock:
            return self._size

    def is_full(self) -> bool:
        with self._lock:
            return self._size >= self.max_depth
