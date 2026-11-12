"""Fake transcriber for tests."""
import asyncio

from app.schemas.transcription import TranscriptionResult


class FakeTranscriber:
    """Deterministic transcriber; optionally fails or takes `delay` seconds."""

    def __init__(self, delay: float = 0.0):
        self.fail = False
        self.delay = delay

    async def transcribe(self, file_path: str) -> TranscriptionResult:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("Transcription failed")
        return TranscriptionResult(
            text="This is a fake transcription for testing.",
            language="en"
        )
