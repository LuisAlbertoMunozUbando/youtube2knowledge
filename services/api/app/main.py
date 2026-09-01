import secrets

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .models import CreateJobRequest, JobRecord, JobResponse
from .pipeline import JobPipeline
from .store import JobStore
from .youtube import YouTubeError, extract_video_id

settings = get_settings()
store = JobStore(settings.jobs_dir)
pipeline = JobPipeline(settings, store)

app = FastAPI(
    title="Youtube2knowledge API",
    version="0.1.0",
    docs_url="/docs" if settings.app_env != "production" else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/jobs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(payload: CreateJobRequest, background_tasks: BackgroundTasks) -> JobResponse:
    try:
        extract_video_id(str(payload.youtube_url))
    except YouTubeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    record = JobRecord(id=secrets.token_hex(8), request=payload)
    store.create(record)
    background_tasks.add_task(pipeline.run, record.id)
    return JobResponse.from_record(record)


@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    try:
        return JobResponse.from_record(store.get(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
