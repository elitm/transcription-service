"""Background worker for processing transcription jobs."""
import asyncio
import logging
from typing import Optional

from app.infrastructure.job_queue import JobQueue
from app.services.event_broadcaster import EventBroadcaster
from app.services.file_storage import FileStorage
from app.services.job_service import JobService
from app.services.transcriber import Transcriber

logger = logging.getLogger(__name__)


class QueueWorker:

    def __init__(self, job_queue: JobQueue, job_service: JobService, file_storage: FileStorage, event_broadcaster: EventBroadcaster, transcriber: Transcriber):
        self.job_queue = job_queue
        self.job_service = job_service
        self.file_storage = file_storage
        self.event_broadcaster = event_broadcaster
        self.transcriber = transcriber
        self.current_job_id: Optional[str] = None
        self._cancelled = False

    async def run_once(self) -> None:
        job_id = self.job_queue.dequeue()
        if job_id is None:
            return

        self.current_job_id = job_id
        try:
            job = self.job_service.get_job(job_id)

            await self.event_broadcaster.publish(job_id, {"status": "processing"})
            self.job_service.mark_processing(job_id)

            result = await self.transcriber.transcribe(job.file_path)

            if self._still_processing(job_id):
                self.job_service.mark_completed(job_id, result)
                await self.event_broadcaster.publish(job_id, {
                    "status": "completed",
                    "text": result.text,
                    "language": result.language,
                })
        except asyncio.CancelledError:
            self._cancelled = True
            raise
        except Exception as e:
            if self._still_processing(job_id):
                error_msg = str(e)
                self.job_service.mark_failed(job_id, error_msg)
                await self.event_broadcaster.publish(job_id, {
                    "status": "failed",
                    "error": error_msg,
                })
        finally:
            if not self._cancelled:
                self.current_job_id = None

    def interrupt_pending_jobs(self) -> None:
        job_ids = [self.current_job_id] if self.current_job_id is not None else []
        while (queued := self.job_queue.dequeue()) is not None:
            job_ids.append(queued)

        for job_id in job_ids:
            try:
                self.job_service.mark_interrupted(job_id)
            except ValueError:
                logger.info("Job %s finished before it could be interrupted", job_id)

        self.current_job_id = None
        self._cancelled = False

    def _still_processing(self, job_id: str) -> bool:
        return self.job_service.get_job(job_id).status == "processing"
