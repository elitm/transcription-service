"""PostgreSQL persistence for jobs."""
import json
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.job import Base, Job

DEFAULT_DATABASE_URL = "postgresql+psycopg://transcriber:transcriber_password@localhost:5432/transcription_db"


def _with_psycopg_driver(db_url: str) -> str:
    if db_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + db_url[len("postgresql://"):]
    return db_url


class JobRepository:
    def __init__(self, db_url: str | None = None):
        db_url = db_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
        self.engine = create_engine(
            _with_psycopg_driver(db_url),
            pool_pre_ping=True,
            json_serializer=lambda value: json.dumps(value, ensure_ascii=False),
        )
        self.SessionLocal = sessionmaker(bind=self.engine)

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)

    def create(self, filename: str, file_size_bytes: int, file_path: str, job_id: str | None = None) -> str:
        session: Session = self.SessionLocal()
        try:
            job = Job(
                original_filename=filename,
                file_size_bytes=file_size_bytes,
                file_path=file_path,
                status="queued",
            )
            if job_id is not None:
                job.id = job_id
            session.add(job)
            session.commit()
            return job.id
        finally:
            session.close()

    def get(self, job_id: str) -> Job:
        session: Session = self.SessionLocal()
        try:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                raise ValueError(f"Job not found: {job_id}")
            session.expunge(job)
            return job
        finally:
            session.close()

    def update(self, job: Job) -> None:
        session: Session = self.SessionLocal()
        try:
            session.merge(job)
            session.commit()
        finally:
            session.close()
