import asyncio
import os
from app.schemas.transcription import TranscriptionResult


class WhisperTranscriber:

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self._model = None

    def _load_model(self):
        """Lazy load the WhisperModel."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                raise RuntimeError("faster_whisper not installed")
            self._model = WhisperModel(self.model_size)
        return self._model

    async def transcribe(self, file_path: str) -> TranscriptionResult:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        model = self._load_model()
        segments, info = await asyncio.to_thread(model.transcribe, file_path)
        text = " ".join(segment.text for segment in segments)
        language = info.language

        return TranscriptionResult(text=text, language=language)
