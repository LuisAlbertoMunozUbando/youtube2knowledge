import json
import os
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from .models import JobRecord


def _slug(value: str, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return slug[:80] or fallback


def _write_atomic(path: Path, content: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _markdown(record: JobRecord, archived_at: datetime) -> str:
    assert record.video is not None
    assert record.transcript is not None

    lines = [
        f"# {record.video.title}",
        "",
        f"- Source: {record.request.youtube_url}",
        f"- YouTube video ID: `{record.video.video_id}`",
        f"- Channel: {record.video.channel or 'Unknown'}",
        f"- Duration: {record.video.duration_seconds or 'Unknown'} seconds",
        f"- Job ID: `{record.id}`",
        f"- Archived at: {archived_at.isoformat()}",
        "",
        "## Grounded questions and answers",
        "",
    ]

    for index, item in enumerate(record.questions, start=1):
        lines.extend(
            [
                f"### {index}. {item.type}: {item.question}",
                "",
                item.answer,
                "",
                "**Evidence from transcript**",
                "",
                f"> {item.evidence.replace(chr(10), ' ')}",
                "",
            ]
        )

    lines.extend(["## Transcript", "", record.transcript, ""])
    return "\n".join(lines)


def archive_job(record: JobRecord, destination: Path) -> list[str]:
    if record.video is None:
        raise ValueError("Cannot archive a job without video metadata")
    if not record.transcript:
        raise ValueError("Cannot archive a job without a transcript")
    if not record.questions:
        raise ValueError("Cannot archive a job without grounded questions")

    destination.mkdir(parents=True, exist_ok=True)
    archived_at = datetime.now(UTC)
    date = archived_at.date().isoformat()
    title = _slug(record.video.title, record.video.video_id)
    stem = f"{date}__{title}__{record.video.video_id}__{record.id}"

    payload = {
        "schema_version": 1,
        "archived_at": archived_at.isoformat(),
        "job_id": record.id,
        "source": {
            "youtube_url": str(record.request.youtube_url),
            **record.video.model_dump(mode="json"),
        },
        "request": record.request.model_dump(mode="json"),
        "transcript": record.transcript,
        "questions": [item.model_dump(mode="json") for item in record.questions],
    }

    json_name = f"{stem}.json"
    markdown_name = f"{stem}.md"
    _write_atomic(
        destination / json_name,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    _write_atomic(destination / markdown_name, _markdown(record, archived_at))
    return [json_name, markdown_name]
