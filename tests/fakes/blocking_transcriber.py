"""Transcriber that holds a job until released, to observe queue behaviour."""
import asyncio
import threading

from app.schemas.transcription import TranscriptionResult


class BlockingTranscriber:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    async def transcribe(self, file_path: str) -> TranscriptionResult:
        self.started.set()
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        return TranscriptionResult(text="", language="en")
