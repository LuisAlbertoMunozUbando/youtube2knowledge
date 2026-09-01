from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, field_validator


class QuestionType(StrEnum):
    WHAT = "What"
    WHICH = "Which"
    WHERE = "Where"
    WHEN = "When"
    HOW = "How"
    WHY = "Why"
    WHO = "Who"
    WHOSE = "Whose"


class JobStage(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class CreateJobRequest(BaseModel):
    youtube_url: HttpUrl
    question_types: list[QuestionType] = Field(min_length=1)
    custom_questions: list[str] = Field(default_factory=list, max_length=20)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    questions_per_type: int = Field(default=2, ge=1, le=5)
    output_language: str = Field(default="auto", pattern=r"^(auto|en|es)$")

    @field_validator("question_types")
    @classmethod
    def unique_types(cls, values: list[QuestionType]) -> list[QuestionType]:
        return list(dict.fromkeys(values))

    @field_validator("custom_questions", "keywords")
    @classmethod
    def clean_text_lists(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        return list(dict.fromkeys(cleaned))


class GeneratedQuestion(BaseModel):
    type: str
    question: str
    answer: str
    evidence: str


class VideoMetadata(BaseModel):
    video_id: str
    title: str
    channel: str | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None


class JobRecord(BaseModel):
    id: str
    stage: JobStage = JobStage.QUEUED
    progress: int = Field(default=0, ge=0, le=100)
    message: str = "Waiting to start"
    request: CreateJobRequest
    video: VideoMetadata | None = None
    transcript: str | None = None
    questions: list[GeneratedQuestion] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobResponse(BaseModel):
    id: str
    stage: JobStage
    progress: int
    message: str
    video: VideoMetadata | None = None
    transcript: str | None = None
    questions: list[GeneratedQuestion] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: JobRecord) -> "JobResponse":
        return cls(**record.model_dump(exclude={"request"}))
