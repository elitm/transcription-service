import pytest
import asyncio
from app.services.transcriber import Transcriber
from app.schemas.transcription import TranscriptionResult
from tests.fakes.fake_transcriber import FakeTranscriber

try:
    from app.services.whisper_transcriber import WhisperTranscriber
    HAS_FASTER_WHISPER = True
except ImportError:
    WhisperTranscriber = None
    HAS_FASTER_WHISPER = False


@pytest.mark.unit
class TestTranscriberProtocol:

    async def test_fake_transcriber_returns_correct_structure(self):
        transcriber = FakeTranscriber()
        result = await transcriber.transcribe("dummy.mp3")

        assert isinstance(result, TranscriptionResult)
        assert isinstance(result.text, str)
        assert isinstance(result.language, str)

    async def test_fake_transcriber_text_not_empty(self):
        transcriber = FakeTranscriber()
        result = await transcriber.transcribe("dummy.mp3")

        assert len(result.text) > 0

    async def test_fake_transcriber_language_valid(self):
        transcriber = FakeTranscriber()
        result = await transcriber.transcribe("dummy.mp3")

        assert len(result.language) == 2
        assert result.language.isalpha()


@pytest.mark.unit
class TestFakeTranscriber:

    async def test_fake_returns_consistent_result(self):
        transcriber = FakeTranscriber()

        result1 = await transcriber.transcribe("file1.mp3")
        result2 = await transcriber.transcribe("file2.mp4")

        assert isinstance(result1, TranscriptionResult)
        assert isinstance(result2, TranscriptionResult)

    async def test_fake_accepts_different_file_types(self):
        transcriber = FakeTranscriber()

        result_mp3 = await transcriber.transcribe("audio.mp3")
        result_mp4 = await transcriber.transcribe("video.mp4")
        result_wav = await transcriber.transcribe("sound.wav")

        assert result_mp3.text
        assert result_mp4.text
        assert result_wav.text


@pytest.mark.unit
@pytest.mark.skipif(not HAS_FASTER_WHISPER, reason="faster-whisper not installed")
class TestWhisperTranscriber:

    async def test_whisper_transcriber_returns_correct_structure(self):
        transcriber = WhisperTranscriber(model_size="tiny")

        assert isinstance(transcriber, Transcriber)
