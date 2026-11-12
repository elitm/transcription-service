import pytest
import asyncio
import tempfile
from pathlib import Path
from app.services.queue_worker import QueueWorker
from app.infrastructure.job_queue import JobQueue
from app.services.job_service import JobService
from app.services.file_storage import FileStorage
from app.services.event_broadcaster import EventBroadcaster
from tests.fakes.fake_transcriber import FakeTranscriber
from tests.fakes.blocking_transcriber import BlockingTranscriber


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def job_queue():
    return JobQueue(max_depth=100)


@pytest.fixture
def job_service(job_repository):
    return JobService(repository=job_repository)


@pytest.fixture
def file_storage(temp_dir):
    return FileStorage(upload_dir=str(temp_dir))


@pytest.fixture
def event_broadcaster():
    return EventBroadcaster()


@pytest.fixture
def fake_transcriber():
    return FakeTranscriber()


@pytest.fixture
def queue_worker(job_queue, job_service, file_storage, event_broadcaster, fake_transcriber):
    return QueueWorker(
        job_queue=job_queue,
        job_service=job_service,
        file_storage=file_storage,
        event_broadcaster=event_broadcaster,
        transcriber=fake_transcriber,
    )


@pytest.mark.unit
class TestQueueWorkerInterrupt:

    def test_interrupt_pending_jobs_marks_queued_jobs_interrupted(self, queue_worker, job_queue, job_service):
        first = job_service.create_job("a.mp3", 10, "/uploads/a")
        second = job_service.create_job("b.mp3", 10, "/uploads/b")
        job_queue.enqueue(first)
        job_queue.enqueue(second)

        queue_worker.interrupt_pending_jobs()

        assert job_service.get_job(first).status == "interrupted"
        assert job_service.get_job(second).status == "interrupted"
        assert job_queue.size() == 0

    async def test_interrupt_pending_jobs_marks_in_flight_job_interrupted(
        self, job_queue, job_service, file_storage, event_broadcaster
    ):
        transcriber = BlockingTranscriber()
        worker = QueueWorker(
            job_queue=job_queue,
            job_service=job_service,
            file_storage=file_storage,
            event_broadcaster=event_broadcaster,
            transcriber=transcriber,
        )
        job_id = job_service.create_job("a.mp3", 10, "/uploads/a")
        job_queue.enqueue(job_id)
        task = asyncio.create_task(worker.run_once())
        while not transcriber.started.is_set():
            await asyncio.sleep(0.01)

        worker.interrupt_pending_jobs()

        assert job_service.get_job(job_id).status == "interrupted"
        transcriber.release.set()
        await task
        assert job_service.get_job(job_id).status == "interrupted"


@pytest.mark.unit
class TestQueueWorkerProcessJob:

    async def test_processes_single_job_from_queue(self, queue_worker, job_queue, job_service, file_storage, temp_dir):
        audio_file = temp_dir / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        job_id = job_service.create_job("test.mp3", 100, str(audio_file))
        queue_worker.job_queue.enqueue(job_id)

        task = asyncio.create_task(queue_worker.run_once())
        result = await asyncio.wait_for(task, timeout=1.0)

        job = job_service.get_job(job_id)

        assert job.status == "completed"
        assert job.result is not None
        assert job.language_detected is not None

    async def test_marks_job_processing_before_transcription(self, queue_worker, job_queue, job_service, file_storage, temp_dir):
        audio_file = temp_dir / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        job_id = job_service.create_job("test.mp3", 100, str(audio_file))
        queue_worker.job_queue.enqueue(job_id)

        await queue_worker.run_once()

        job = job_service.get_job(job_id)
        assert job.started_at is not None

    async def test_broadcasts_events_during_processing(self, queue_worker, job_queue, job_service, file_storage, event_broadcaster, temp_dir):
        audio_file = temp_dir / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        job_id = job_service.create_job("test.mp3", 100, str(audio_file))
        queue_worker.job_queue.enqueue(job_id)

        events = []
        async def collect_events():
            try:
                async for evt in event_broadcaster.subscribe(job_id):
                    events.append(evt)
                    if len(events) >= 2:
                        break
            except ValueError:
                pass

        event_task = asyncio.create_task(collect_events())
        await asyncio.sleep(0.01)

        await queue_worker.run_once()

        try:
            await asyncio.wait_for(event_task, timeout=0.5)
        except asyncio.TimeoutError:
            event_task.cancel()

        assert len(events) >= 1
        assert any(evt.get("status") == "processing" for evt in events)


@pytest.mark.unit
class TestQueueWorkerErrorHandling:

    async def test_marks_job_failed_on_transcription_error(self, queue_worker, job_queue, job_service, file_storage, temp_dir):
        audio_file = temp_dir / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        job_id = job_service.create_job("test.mp3", 100, str(audio_file))
        queue_worker.job_queue.enqueue(job_id)

        queue_worker.transcriber.fail = True

        await queue_worker.run_once()

        job = job_service.get_job(job_id)
        assert job.status == "failed"
        assert job.error is not None

    async def test_does_not_crash_on_queue_empty(self, queue_worker):
        result = await queue_worker.run_once()
        assert result is None
