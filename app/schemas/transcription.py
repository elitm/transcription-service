from pydantic import BaseModel, Field


class TranscriptionResult(BaseModel):

    text: str = Field(..., description="Transcribed text")
    language: str = Field(..., description="Detected language code (e.g., en, es, fr)")
