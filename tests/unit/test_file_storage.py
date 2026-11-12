import pytest
import os
import tempfile
from pathlib import Path
from app.services.file_storage import FileStorage


@pytest.fixture
def temp_upload_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def file_storage(temp_upload_dir):
    return FileStorage(upload_dir=temp_upload_dir)


@pytest.mark.unit
class TestFileStorageSave:

    def test_save_creates_file(self, file_storage, temp_upload_dir):
        job_id = "job-123"
        file_data = b"test audio data"

        file_path = file_storage.save(job_id, file_data)

        assert os.path.exists(file_path)
        assert file_path.endswith(job_id)

    def test_save_returns_correct_path(self, file_storage, temp_upload_dir):
        job_id = "job-456"
        file_data = b"audio content"

        file_path = file_storage.save(job_id, file_data)

        assert file_path.startswith(temp_upload_dir)
        assert job_id in file_path

    def test_save_writes_file_content(self, file_storage):
        job_id = "job-789"
        file_data = b"test content here"

        file_path = file_storage.save(job_id, file_data)

        with open(file_path, "rb") as f:
            assert f.read() == file_data

    def test_save_multiple_files(self, file_storage):
        job_id_1 = "job-1"
        job_id_2 = "job-2"
        data_1 = b"file 1"
        data_2 = b"file 2"

        path_1 = file_storage.save(job_id_1, data_1)
        path_2 = file_storage.save(job_id_2, data_2)

        assert path_1 != path_2
        assert os.path.exists(path_1)
        assert os.path.exists(path_2)


@pytest.mark.unit
class TestFileStorageValidation:

    def test_save_with_valid_extension(self, file_storage):
        valid_extensions = ["mp3", "wav", "m4a", "mp4", "mov"]

        for ext in valid_extensions:
            job_id = f"job-{ext}"
            file_data = b"test"
            file_path = file_storage.save(job_id, file_data, f"file.{ext}")
            assert os.path.exists(file_path)

    def test_save_rejects_invalid_extension(self, file_storage):
        job_id = "job-invalid"
        file_data = b"test"

        with pytest.raises(ValueError):
            file_storage.save(job_id, file_data, "file.txt")

    def test_save_case_insensitive_extension(self, file_storage):
        job_id = "job-case"
        file_data = b"test"

        file_path = file_storage.save(job_id, file_data, "FILE.MP3")

        assert os.path.exists(file_path)
