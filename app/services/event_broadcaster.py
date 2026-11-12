"""Server-Sent Events fan-out: one subscriber per job."""
import asyncio
from typing import AsyncIterator, Dict


class EventBroadcaster:
    def __init__(self):
        self._subscribers: Dict[str, asyncio.Queue] = {}

    async def subscribe(self, job_id: str) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue()

        if job_id in self._subscribers:
            raise ValueError(f"Job {job_id} already has an active subscriber")
        self._subscribers[job_id] = queue

        try:
            while True:
                yield await queue.get()
        finally:
            if self._subscribers.get(job_id) is queue:
                del self._subscribers[job_id]

    async def publish(self, job_id: str, event: dict) -> None:
        queue = self._subscribers.get(job_id)
        if queue is None:
            return
        await queue.put(event)
