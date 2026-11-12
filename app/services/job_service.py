"""Job service for managing transcription job state machine."""
from datetime import datetime
from app.data.job_repository import JobRepository
from app.models.job import Job
from app.schemas.transcription import TranscriptionResult


VALID_TRANSITIONS = {
    "queued": {"processing", "interrupted"},
    "processing": {"completed", "failed", "interrupted"},
    "completed": set(),
    "failed": set(),
    "interrupted": set(),
}


class JobService:

    def __init__(self, repository: JobRepository):
        self.repository = repository

    def init_db(self):
        self.repository.init_db()

    def create_job(self, filename: str, file_size_bytes: int, file_path: str, job_id: str | None = None) -> str:
        return self.repository.create(filename, file_size_bytes, file_path, job_id=job_id)

    def get_job(self, job_id: str) -> Job:
        return self.repository.get(job_id)

    def mark_processing(self, job_id: str) -> None:
        job = self.repository.get(job_id)
        self._validate_transition(job.status, "processing")
        job.status = "processing"
        job.started_at = datetime.utcnow()
        self.repository.update(job)

    def mark_completed(self, job_id: str, result: TranscriptionResult) -> None:
        job = self.repository.get(job_id)
        self._validate_transition(job.status, "completed")
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.result = result.model_dump()
        job.language_detected = result.language
        self.repository.update(job)

    def mark_failed(self, job_id: str, error_msg: str) -> None:
        job = self.repository.get(job_id)
        self._validate_transition(job.status, "failed")
        job.status = "failed"
        job.error = error_msg
        self.repository.update(job)

    def mark_interrupted(self, job_id: str) -> None:
        job = self.repository.get(job_id)
        self._validate_transition(job.status, "interrupted")
        job.status = "interrupted"
        self.repository.update(job)

    def _validate_transition(self, from_status: str, to_status: str) -> None:
        if to_status not in VALID_TRANSITIONS.get(from_status, set()):
            raise ValueError(
                f"Invalid state transition: {from_status} -> {to_status}"
            )
