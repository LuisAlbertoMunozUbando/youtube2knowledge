import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from .models import JobRecord


class JobStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, job_id: str) -> Path:
        if not job_id.isalnum():
            raise KeyError(job_id)
        return self.directory / f"{job_id}.json"

    def create(self, record: JobRecord) -> JobRecord:
        path = self._path(record.id)
        with self._lock:
            if path.exists():
                raise ValueError(f"Job {record.id} already exists")
            self._write(path, record)
        return record

    def get(self, job_id: str) -> JobRecord:
        path = self._path(job_id)
        with self._lock:
            if not path.exists():
                raise KeyError(job_id)
            return JobRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, record: JobRecord) -> JobRecord:
        record.updated_at = datetime.now(UTC)
        with self._lock:
            self._write(self._path(record.id), record)
        return record

    @staticmethod
    def _write(path: Path, record: JobRecord) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
