from pathlib import Path

import pytest

from app.config import Settings
from app.models import (
    CreateJobRequest,
    GeneratedQuestion,
    JobRecord,
    JobStage,
    VideoMetadata,
)
from app.pipeline import JobPipeline
from app.store import JobStore


def record() -> JobRecord:
    return JobRecord(
        id="abc123",
        request=CreateJobRequest(
            youtube_url="https://youtu.be/dQw4w9WgXcQ",
            question_types=["What"],
        ),
    )


@pytest.mark.asyncio
async def test_pipeline_completes_and_cleans_workdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(app_data_dir=tmp_path, transcription_provider="openai")
    store = JobStore(settings.jobs_dir)
    store.create(record())

    def fake_inspect(url: str, max_minutes: int) -> VideoMetadata:
        return VideoMetadata(video_id="dQw4w9WgXcQ", title="Test video")

    def fake_download(url: str, destination: Path) -> Path:
        audio = destination / "audio.mp3"
        audio.write_bytes(b"audio")
        return audio

    monkeypatch.setattr("app.pipeline.inspect_video", fake_inspect)
    monkeypatch.setattr("app.pipeline.download_audio", fake_download)
    monkeypatch.setattr("app.pipeline.transcribe", lambda *args: "Source transcript")
    monkeypatch.setattr(
        "app.pipeline.generate_questions",
        lambda *args: [
            GeneratedQuestion(
                type="What",
                question="What is tested?",
                answer="The pipeline.",
                evidence="Source transcript",
            )
        ],
    )

    await JobPipeline(settings, store).run("abc123")

    completed = store.get("abc123")
    assert completed.stage == JobStage.COMPLETED
    assert completed.progress == 100
    assert completed.transcript == "Source transcript"
    assert len(completed.questions) == 1
    assert not (settings.work_dir / "abc123").exists()


@pytest.mark.asyncio
async def test_pipeline_persists_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(app_data_dir=tmp_path, transcription_provider="openai")
    store = JobStore(settings.jobs_dir)
    store.create(record())
    monkeypatch.setattr(
        "app.pipeline.inspect_video",
        lambda *args: (_ for _ in ()).throw(RuntimeError("Video unavailable")),
    )

    await JobPipeline(settings, store).run("abc123")

    failed = store.get("abc123")
    assert failed.stage == JobStage.FAILED
    assert failed.error == "Video unavailable"
    assert not (settings.work_dir / "abc123").exists()
