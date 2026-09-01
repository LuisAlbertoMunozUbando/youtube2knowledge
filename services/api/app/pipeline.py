import asyncio
import shutil
from collections.abc import Callable
from pathlib import Path

from .archive import archive_job
from .config import Settings
from .models import JobRecord, JobStage
from .providers.questions import generate_questions
from .providers.transcription import transcribe
from .store import JobStore
from .youtube import download_audio, inspect_video


class JobPipeline:
    def __init__(self, settings: Settings, store: JobStore) -> None:
        self.settings = settings
        self.store = store
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)

    def _update(
        self,
        record: JobRecord,
        stage: JobStage,
        progress: int,
        message: str,
    ) -> None:
        record.stage = stage
        record.progress = progress
        record.message = message
        self.store.save(record)

    async def _blocking(self, function: Callable, *args):
        return await asyncio.to_thread(function, *args)

    async def run(self, job_id: str) -> None:
        async with self._semaphore:
            record = self.store.get(job_id)
            work_dir = self.settings.work_dir / job_id
            work_dir.mkdir(parents=True, exist_ok=True)
            try:
                self._update(record, JobStage.DOWNLOADING, 10, "Inspecting video")
                record.video = await self._blocking(
                    inspect_video,
                    str(record.request.youtube_url),
                    self.settings.max_video_minutes,
                )
                self.store.save(record)

                self._update(record, JobStage.DOWNLOADING, 25, "Extracting audio")
                audio_path: Path = await self._blocking(
                    download_audio,
                    str(record.request.youtube_url),
                    work_dir,
                )

                self._update(record, JobStage.TRANSCRIBING, 45, "Transcribing audio")
                record.transcript = await self._blocking(
                    transcribe,
                    audio_path,
                    self.settings,
                    "auto",
                )
                self.store.save(record)

                self._update(record, JobStage.GENERATING, 75, "Generating questions")
                record.questions = await self._blocking(
                    generate_questions,
                    record.transcript,
                    record.request,
                    self.settings,
                )
                self._update(record, JobStage.ARCHIVING, 90, "Archiving evidence")
                record.archive_files = await self._blocking(
                    archive_job,
                    record,
                    self.settings.drive_outbox_dir,
                )
                self._update(record, JobStage.COMPLETED, 100, "Knowledge set ready")
            except Exception as exc:
                record.error = str(exc)
                self._update(record, JobStage.FAILED, record.progress, "Processing failed")
            finally:
                shutil.rmtree(work_dir, ignore_errors=True)

    def queue_generation_retry(self, job_id: str) -> JobRecord:
        record = self.store.get(job_id)
        if not record.transcript:
            raise ValueError("The job has no saved transcript")
        record.error = None
        self._update(record, JobStage.GENERATING, 75, "Regenerating grounded questions")
        return record

    async def run_generation(self, job_id: str) -> None:
        async with self._semaphore:
            record = self.store.get(job_id)
            try:
                if not record.transcript:
                    raise ValueError("The job has no saved transcript")
                record.questions = await self._blocking(
                    generate_questions,
                    record.transcript,
                    record.request,
                    self.settings,
                )
                self._update(record, JobStage.ARCHIVING, 90, "Archiving evidence")
                record.archive_files = await self._blocking(
                    archive_job,
                    record,
                    self.settings.drive_outbox_dir,
                )
                self._update(record, JobStage.COMPLETED, 100, "Knowledge set ready")
            except Exception as exc:
                record.error = str(exc)
                self._update(record, JobStage.FAILED, record.progress, "Processing failed")
