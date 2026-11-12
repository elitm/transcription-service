"""File storage for uploaded media."""
import os
from pathlib import Path


ALLOWED_EXTENSIONS = {"mp3", "wav", "m4a", "mp4", "mov"}


class FileStorage:
    def __init__(self, upload_dir: str = "/uploads"):
        self.upload_dir = upload_dir
        self._ensure_dir_exists()

    def _ensure_dir_exists(self):
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)

    def save(self, job_id: str, file_data: bytes, filename: str = None) -> str:
        if filename:
            self._validate_extension(filename)

        file_path = os.path.join(self.upload_dir, job_id)

        with open(file_path, "wb") as f:
            f.write(file_data)

        return file_path

    def _validate_extension(self, filename: str) -> None:
        ext = Path(filename).suffix.lstrip(".").lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"Invalid file extension: .{ext}. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )
