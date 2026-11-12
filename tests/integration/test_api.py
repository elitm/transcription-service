"""Integration tests for the API: real app, real worker thread, PostgreSQL."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.job_queue import JobQueue
from app.main import create_app
from tests.fakes.blocking_transcriber import BlockingTranscriber
from tests.fakes.fake_transcriber import FakeTranscriber

FINISHED = {"completed", "failed"}


def upload(client: TestClient, filename: str = "test.mp3", content_type: str = "audio/mpeg"):
    return client.post("/jobs", files={"file": (filename, b"fake audio data", content_type)})


def wait_until_finished(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in FINISHED:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s: {job}")


@pytest.fixture
def client(test_client):
    return test_client


@pytest.mark.integration
class TestUploadEndpoint:

    def test_upload_returns_202_with_job_id(self, client):
        response = upload(client)

        assert response.status_code == 202
        assert isinstance(response.json()["job_id"], str)

    def test_upload_rejects_invalid_extension(self, client):
        response = upload(client, "notes.txt", "text/plain")

        assert response.status_code == 400

    def test_upload_requires_file(self, client):
        assert client.post("/jobs").status_code == 422

    def test_upload_returns_503_when_queue_is_full(self, test_job_service, test_file_storage, test_broadcaster):
        transcriber = BlockingTranscriber()
        app = create_app(
            job_service=test_job_service,
            file_storage=test_file_storage,
            job_queue=JobQueue(max_depth=1),
            event_broadcaster=test_broadcaster,
            transcriber=transcriber,
        )
        try:
            with TestClient(app) as client:
                assert upload(client).status_code == 202
                assert transcriber.started.wait(timeout=5), "worker never picked up the first job"
                assert upload(client).status_code == 202

                response = upload(client)

                assert response.status_code == 503
                transcriber.release.set()
        finally:
            transcriber.release.set()


@pytest.mark.integration
class TestGetJobEndpoint:

    def test_get_returns_job_status(self, client):
        job_id = upload(client).json()["job_id"]

        response = client.get(f"/jobs/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job_id
        assert data["status"] in {"queued", "processing", "completed"}
        assert data["created_at"]

    def test_get_returns_404_for_missing_job(self, client):
        assert client.get("/jobs/nonexistent").status_code == 404

    def test_background_worker_completes_job(self, client):
        job_id = upload(client).json()["job_id"]

        job = wait_until_finished(client, job_id)

        assert job["status"] == "completed"
        assert job["language_detected"] == "en"
        assert job["result"]["text"] == "This is a fake transcription for testing."
        assert job["started_at"] and job["completed_at"]

    def test_unicode_filename_round_trips_through_database(self, client):
        filename = "קרן מור ומוני מושונוב בקצרים.mp3"
        job_id = upload(client, filename).json()["job_id"]

        job = client.get(f"/jobs/{job_id}").json()

        assert job["original_filename"] == filename


@pytest.mark.integration
class TestSubscribeEndpoint:

    def test_subscribe_streams_final_status_of_finished_job(self, client):
        job_id = upload(client).json()["job_id"]
        wait_until_finished(client, job_id)

        response = client.get(f"/jobs/{job_id}/subscribe")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.text.startswith("data: ")
        assert '"status": "completed"' in response.text

    def test_subscribe_streams_events_until_job_finishes(self, test_job_service, test_file_storage, test_broadcaster):
        app = create_app(
            job_service=test_job_service,
            file_storage=test_file_storage,
            job_queue=JobQueue(max_depth=10),
            event_broadcaster=test_broadcaster,
            transcriber=FakeTranscriber(delay=0.3),
            sse_keepalive_seconds=0.2,
        )
        with TestClient(app) as client:
            job_id = upload(client).json()["job_id"]

            response = client.get(f"/jobs/{job_id}/subscribe")

        events = [json.loads(line[len("data: "):]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert events[-1]["status"] == "completed"
        assert events[-1]["text"] == "This is a fake transcription for testing."

    def test_subscribe_returns_404_for_missing_job(self, client):
        assert client.get("/jobs/nonexistent/subscribe").status_code == 404


@pytest.mark.integration
class TestShutdown:

    def test_shutdown_marks_in_flight_and_queued_jobs_interrupted(self, test_job_service, test_file_storage, test_broadcaster):
        transcriber = BlockingTranscriber()
        app = create_app(
            job_service=test_job_service,
            file_storage=test_file_storage,
            job_queue=JobQueue(max_depth=10),
            event_broadcaster=test_broadcaster,
            transcriber=transcriber,
            shutdown_grace_seconds=0.2,
        )
        try:
            with TestClient(app) as client:
                in_flight = upload(client).json()["job_id"]
                assert transcriber.started.wait(timeout=5)
                queued = upload(client).json()["job_id"]
        finally:
            transcriber.release.set()

        assert test_job_service.get_job(in_flight).status == "interrupted"
        assert test_job_service.get_job(queued).status == "interrupted"
