"""Integration tests for real WhisperTranscriber with faster-whisper."""
import pytest
import os
import tempfile
import wave
from app.schemas.transcription import TranscriptionResult

import importlib.util
from app.services.whisper_transcriber import WhisperTranscriber

HAS_FASTER_WHISPER = importlib.util.find_spec("faster_whisper") is not None


@pytest.fixture
def test_audio_file():
    """Create a minimal test audio file."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = f.name

    try:
        with wave.open(temp_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(b"\x00" * 32000)
        yield temp_path
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.integration
@pytest.mark.skipif(not HAS_FASTER_WHISPER, reason="faster-whisper not installed")
class TestWhisperTranscriberReal:
    """Test real faster-whisper transcription."""

    async def test_whisper_returns_transcription_result(self, test_audio_file):
        """Real transcriber should return TranscriptionResult."""
        transcriber = WhisperTranscriber(model_size="tiny")
        result = await transcriber.transcribe(test_audio_file)

        assert isinstance(result, TranscriptionResult)
        assert isinstance(result.text, str)
        assert isinstance(result.language, str)

    async def test_whisper_raises_on_missing_file(self):
        """Should raise FileNotFoundError for missing file."""
        transcriber = WhisperTranscriber(model_size="tiny")

        with pytest.raises(FileNotFoundError):
            await transcriber.transcribe("/nonexistent/file.wav")
