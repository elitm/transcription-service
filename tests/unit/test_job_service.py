import pytest
from app.services.job_service import JobService
from app.schemas.transcription import TranscriptionResult


@pytest.fixture
def job_service(job_repository):
    return JobService(repository=job_repository)


@pytest.mark.unit
class TestJobServiceCreateWithId:

    def test_create_job_uses_given_id(self, job_service):
        job_id = job_service.create_job(
            filename="audio.mp3",
            file_size_bytes=5000,
            file_path="/uploads/given-id",
            job_id="given-id",
        )

        assert job_id == "given-id"
        assert job_service.get_job("given-id").file_path == "/uploads/given-id"


@pytest.mark.unit
class TestJobServiceCreate:

    def test_create_job_returns_job_id(self, job_service):
        job_id = job_service.create_job(
            filename="audio.mp3",
            file_size_bytes=5000,
            file_path="/uploads/job-1"
        )

        assert job_id
        assert isinstance(job_id, str)

    def test_create_job_stores_metadata(self, job_service):
        job_id = job_service.create_job(
            filename="audio.mp3",
            file_size_bytes=5000,
            file_path="/uploads/job-1"
        )

        job = job_service.get_job(job_id)

        assert job.original_filename == "audio.mp3"
        assert job.file_path == "/uploads/job-1"
        assert job.file_size_bytes == 5000

    def test_create_job_sets_queued_status(self, job_service):
        job_id = job_service.create_job(
            filename="audio.mp3",
            file_size_bytes=1000,
            file_path="/uploads/job-1"
        )

        job = job_service.get_job(job_id)

        assert job.status == "queued"


@pytest.mark.unit
class TestJobServiceGetJob:

    def test_get_job_returns_complete_state(self, job_service):
        job_id = job_service.create_job(
            filename="test.wav",
            file_size_bytes=2000,
            file_path="/uploads/test"
        )

        job = job_service.get_job(job_id)

        assert job.id == job_id
        assert job.status == "queued"
        assert job.created_at is not None
        assert job.started_at is None

    def test_get_nonexistent_job_raises_error(self, job_service):
        with pytest.raises(Exception):
            job_service.get_job("nonexistent-id")


@pytest.mark.unit
class TestJobServiceStateTransitions:

    def test_mark_processing_transitions_state(self, job_service):
        job_id = job_service.create_job(
            filename="audio.mp3",
            file_size_bytes=1000,
            file_path="/uploads/job"
        )

        job_service.mark_processing(job_id)
        job = job_service.get_job(job_id)

        assert job.status == "processing"
        assert job.started_at is not None

    def test_mark_completed_stores_result(self, job_service):
        job_id = job_service.create_job(
            filename="audio.mp3",
            file_size_bytes=1000,
            file_path="/uploads/job"
        )
        job_service.mark_processing(job_id)

        result = TranscriptionResult(text="Hello world", language="en")
        job_service.mark_completed(job_id, result)

        job = job_service.get_job(job_id)

        assert job.status == "completed"
        assert job.result["text"] == "Hello world"
        assert job.language_detected == "en"
        assert job.completed_at is not None

    def test_mark_failed_stores_error(self, job_service):
        job_id = job_service.create_job(
            filename="audio.mp3",
            file_size_bytes=1000,
            file_path="/uploads/job"
        )
        job_service.mark_processing(job_id)

        job_service.mark_failed(job_id, "Model error: out of memory")

        job = job_service.get_job(job_id)

        assert job.status == "failed"
        assert job.error == "Model error: out of memory"

    def test_mark_interrupted_on_shutdown(self, job_service):
        job_id = job_service.create_job(
            filename="audio.mp3",
            file_size_bytes=1000,
            file_path="/uploads/job"
        )
        job_service.mark_processing(job_id)

        job_service.mark_interrupted(job_id)

        job = job_service.get_job(job_id)

        assert job.status == "interrupted"


@pytest.mark.unit
class TestJobServiceValidation:

    def test_invalid_state_transition_raises_error(self, job_service):
        job_id = job_service.create_job(
            filename="audio.mp3",
            file_size_bytes=1000,
            file_path="/uploads/job"
        )
        job_service.mark_processing(job_id)
        job_service.mark_completed(job_id, TranscriptionResult(text="Done", language="en"))

        with pytest.raises(Exception):
            job_service.mark_processing(job_id)
