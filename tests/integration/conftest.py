"""Integration fixtures: the real app wired to PostgreSQL and a fake transcriber."""
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.job_queue import JobQueue
from app.main import create_app
from app.services.event_broadcaster import EventBroadcaster
from app.services.file_storage import FileStorage
from app.services.job_service import JobService
from tests.fakes.fake_transcriber import FakeTranscriber


@pytest.fixture
def test_job_service(job_repository):
    return JobService(repository=job_repository)


@pytest.fixture
def test_file_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield FileStorage(upload_dir=tmpdir)


@pytest.fixture
def test_queue():
    return JobQueue(max_depth=100)


@pytest.fixture
def test_broadcaster():
    return EventBroadcaster()


@pytest.fixture
def test_transcriber():
    return FakeTranscriber()


@pytest.fixture
def test_client(test_job_service, test_file_storage, test_queue, test_broadcaster, test_transcriber):
    app = create_app(
        job_service=test_job_service,
        file_storage=test_file_storage,
        job_queue=test_queue,
        event_broadcaster=test_broadcaster,
        transcriber=test_transcriber,
    )
    with TestClient(app) as client:
        yield client
