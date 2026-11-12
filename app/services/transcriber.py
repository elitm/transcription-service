"""Transcriber interface."""
from typing import Protocol, runtime_checkable
from app.schemas.transcription import TranscriptionResult


@runtime_checkable
class Transcriber(Protocol):

    async def transcribe(self, file_path: str) -> TranscriptionResult:
        ...
