"""FastAPI application: upload media, transcribe in the background, stream job status."""
import asyncio
import contextlib
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.data.job_repository import JobRepository
from app.infrastructure.job_queue import JobQueue, QueueFullError
from app.models.job import Job
from app.services.event_broadcaster import EventBroadcaster
from app.services.file_storage import ALLOWED_EXTENSIONS, FileStorage
from app.services.job_service import JobService
from app.services.queue_worker import QueueWorker
from app.services.transcriber import Transcriber
from app.services.whisper_transcriber import WhisperTranscriber

FINISHED_STATUSES = {"completed", "failed", "interrupted"}
WORKER_POLL_SECONDS = 0.1

logger = logging.getLogger(__name__)


def create_app(
    job_service: JobService,
    file_storage: FileStorage,
    job_queue: JobQueue,
    event_broadcaster: EventBroadcaster,
    transcriber: Transcriber,
    *,
    sse_keepalive_seconds: float = 15.0,
    shutdown_grace_seconds: float = 5.0,
) -> FastAPI:
    worker = QueueWorker(
        job_queue=job_queue,
        job_service=job_service,
        file_storage=file_storage,
        event_broadcaster=event_broadcaster,
        transcriber=transcriber,
    )

    async def worker_loop() -> None:
        while True:
            try:
                await worker.run_once()
            except Exception:
                logger.exception("Worker iteration failed")
            await asyncio.sleep(WORKER_POLL_SECONDS)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        job_service.init_db()
        worker_task = asyncio.create_task(worker_loop())
        yield
        worker_task.cancel()
        try:
            await asyncio.wait_for(worker_task, timeout=shutdown_grace_seconds)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        worker.interrupt_pending_jobs()

    app = FastAPI(title="Transcription Service", lifespan=lifespan)

    def get_job_or_404(job_id: str) -> Job:
        try:
            return job_service.get_job(job_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Job not found")

    @app.post("/jobs", status_code=202)
    async def upload_job(file: UploadFile = File(...)) -> dict:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename required")
        extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Unsupported file type")
        if job_queue.is_full():
            raise HTTPException(status_code=503, detail="Queue is full, retry later")

        file_data = await file.read()
        job_id = str(uuid.uuid4())
        file_path = file_storage.save(job_id, file_data, file.filename)
        job_service.create_job(file.filename, len(file_data), file_path, job_id=job_id)

        try:
            job_queue.enqueue(job_id)
        except QueueFullError:
            job_service.mark_interrupted(job_id)
            raise HTTPException(status_code=503, detail="Queue is full, retry later")

        return {"job_id": job_id}

    @app.get("/jobs/{job_id}")
    async def get_job(job_id: str) -> dict:
        job = get_job_or_404(job_id)
        return {
            "id": job.id,
            "status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "language_detected": job.language_detected,
            "result": job.result,
            "error": job.error,
            "original_filename": job.original_filename,
            "file_size_bytes": job.file_size_bytes,
        }

    @app.get("/jobs/{job_id}/subscribe")
    async def subscribe_job(job_id: str) -> StreamingResponse:
        get_job_or_404(job_id)
        return StreamingResponse(job_events(job_id), media_type="text/event-stream")

    async def job_events(job_id: str) -> AsyncIterator[str]:
        job = job_service.get_job(job_id)
        if job.status in FINISHED_STATUSES:
            yield sse(final_event(job))
            return

        events = event_broadcaster.subscribe(job_id)
        next_event = None
        try:
            while True:
                if next_event is None:
                    next_event = asyncio.ensure_future(anext(events))
                done, _ = await asyncio.wait({next_event}, timeout=sse_keepalive_seconds)
                if not done:
                    job = job_service.get_job(job_id)
                    if job.status in FINISHED_STATUSES:
                        yield sse(final_event(job))
                        return
                    yield ": keep-alive\n\n"
                    continue
                event, next_event = next_event.result(), None
                yield sse(event)
                if event.get("status") in FINISHED_STATUSES:
                    return
        except ValueError as exc:
            yield sse({"status": "error", "error": str(exc)})
        finally:
            if next_event is not None and not next_event.done():
                next_event.cancel()
                with contextlib.suppress(asyncio.CancelledError, ValueError):
                    await next_event
            await events.aclose()

    return app


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def final_event(job: Job) -> dict:
    if job.status == "completed":
        return {"status": "completed", **(job.result or {})}
    return {"status": job.status, "error": job.error}


def build_app() -> FastAPI:
    return create_app(
        job_service=JobService(repository=JobRepository()),
        file_storage=FileStorage(),
        job_queue=JobQueue(max_depth=100),
        event_broadcaster=EventBroadcaster(),
        transcriber=WhisperTranscriber(),
    )
