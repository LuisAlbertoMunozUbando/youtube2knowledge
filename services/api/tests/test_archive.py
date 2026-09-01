import json
from pathlib import Path

from app.archive import archive_job
from app.models import (
    CreateJobRequest,
    GeneratedQuestion,
    JobRecord,
    VideoMetadata,
)


def test_archive_contains_source_answers_and_exact_evidence(tmp_path: Path) -> None:
    record = JobRecord(
        id="job123",
        request=CreateJobRequest(
            youtube_url="https://youtu.be/dQw4w9WgXcQ",
            question_types=["What"],
            keywords=["GPU"],
        ),
        video=VideoMetadata(
            video_id="dQw4w9WgXcQ",
            title="¿Qué es NVIDIA?",
            channel="Example channel",
            duration_seconds=42,
        ),
        transcript="NVIDIA builds accelerated computing platforms.",
        questions=[
            GeneratedQuestion(
                type="What",
                question="What does NVIDIA build?",
                answer="Accelerated computing platforms.",
                evidence="NVIDIA builds accelerated computing platforms.",
            )
        ],
    )

    filenames = archive_job(record, tmp_path)

    assert len(filenames) == 2
    json_path = next(tmp_path / name for name in filenames if name.endswith(".json"))
    markdown_path = next(
        tmp_path / name for name in filenames if name.endswith(".md")
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert payload["schema_version"] == 1
    assert payload["source"]["youtube_url"] == "https://youtu.be/dQw4w9WgXcQ"
    assert payload["transcript"] == record.transcript
    assert payload["questions"][0]["answer"] == record.questions[0].answer
    assert payload["questions"][0]["evidence"] == record.questions[0].evidence
    assert "Source: https://youtu.be/dQw4w9WgXcQ" in markdown
    assert "**Evidence from transcript**" in markdown
    assert record.questions[0].evidence in markdown
