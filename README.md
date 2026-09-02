# Youtube2knowledge

Turn a YouTube video into a transcript and a grounded set of questions and
answers. Choose the question lenses you care about, add focus keywords, and ask
your own questions.

Project: <https://github.com/LuisAlbertoMunozUbando/youtube2knowledge>

## What it does

1. Validates a single YouTube video URL.
2. Extracts its audio with `yt-dlp` and `ffmpeg`.
3. Transcribes it with local Whisper or a transcription API.
4. Generates evidence-backed questions for any selection of:
   **What, Which, Where, When, How, Why, Who, Whose**.
5. Answers custom questions and prioritizes user-provided keywords.
6. Returns a downloadable JSON knowledge set and the source transcript.

The model is instructed to use only the transcript and every generated answer
includes a short source excerpt.

The browser remembers the latest job across refreshes, keeps polling after
temporary network errors, and can retry question generation from the saved
transcript without downloading the video again.

## Architecture

```text
Browser
  └─ Next.js web app (Vercel)
       └─ FastAPI job API (Spark through Cloudflare Tunnel)
            ├─ yt-dlp + ffmpeg
            ├─ Whisper local or transcription API
            └─ OpenAI-compatible LLM (OpenAI, NVIDIA NIM, etc.)
```

Media processing deliberately stays outside Vercel and Cloudflare Workers. It
is long-running, needs `ffmpeg`, and can require GPU access. The API persists
job state as atomic JSON files so browser polling survives page refreshes and
normal application restarts.

## Repository

```text
apps/web/             Next.js 16 interface
services/api/         FastAPI processing service
deploy/cloudflare/    Tunnel and edge guidance
deploy/systemd/       Spark service unit
.github/workflows/    CI for API and web
```

## Quick start

### Requirements

- Node.js 24+
- Python 3.11+
- `ffmpeg`
- An OpenAI-compatible chat endpoint
- A transcription provider, either API-based or local Whisper

### Configure

```bash
cp .env.example .env
```

For API transcription, set:

```dotenv
TRANSCRIPTION_PROVIDER=openai
TRANSCRIPTION_API_KEY=...
```

For local Whisper:

```bash
cd services/api
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,local-whisper]"
```

Then set `TRANSCRIPTION_PROVIDER=local_whisper`. `WHISPER_DEVICE`,
`WHISPER_MODEL`, and `WHISPER_COMPUTE_TYPE` control the runtime.

Configure question generation with any OpenAI-compatible endpoint:

```dotenv
LLM_API_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=...
LLM_MODEL=gpt-4.1-mini
```

### Run locally

API:

```bash
cd services/api
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Web:

```bash
cd apps/web
npm install
npm run dev
```

Open `http://localhost:3000`. API documentation is available at
`http://localhost:8000/docs` outside production.

Alternatively, run both services:

```bash
docker compose up --build
```

The compose deployment publishes the API on port `8020` by default. Change
`API_PORT` only if that port is already assigned.

### NVIDIA DGX Spark

The Spark deployment keeps transcription and question generation on the GB10:

- NVIDIA Speech NIM with Parakeet 1.1B RNNT Multilingual for ASR.
- vLLM with an OpenAI-compatible local endpoint for question generation.
- The FastAPI service remains a lightweight orchestrator and does not need
  direct GPU access.

Copy `.env.spark.example` to `.env`, add an NGC API key, authenticate Docker to
`nvcr.io`, and launch the Spark override:

```bash
docker compose -f docker-compose.yml -f docker-compose.spark.yml up -d --build
```

The ASR and LLM ports bind only to loopback. Only FastAPI port `8020` is intended
for publication through Cloudflare Tunnel. The initial model download and NIM
optimization can take 30 minutes or longer.

The ASR service is pinned to the prebuilt multilingual offline profile for the
DGX Spark GB10. Audio is normalized to mono 16 kHz PCM WAV, the input format
validated against Speech NIM, before transcription. A one-shot initializer makes
the persistent NIM cache writable before the ASR container starts. The vLLM
service disables Hugging Face Xet downloads and uses the standard HTTP path to
avoid CAS reconstruction failures while fetching model weights. Its DNS
override is scoped to the LLM container so a host-level sinkhole response for
`huggingface.co` cannot block model downloads or alter other Spark services.

The preliminary model-architecture appendix is available as reusable LaTeX in
[`docs/whitepaper/appendix-model-architecture-content.tex`](docs/whitepaper/appendix-model-architecture-content.tex),
with a standalone wrapper and compiled PDF for visual review.

## API

Create a job:

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H 'content-type: application/json' \
  -d '{
    "youtube_url": "https://youtube.com/watch?v=VIDEO_ID",
    "question_types": ["What", "How", "Why"],
    "custom_questions": ["What is the central claim?"],
    "keywords": ["robotics", "investment"],
    "questions_per_type": 2,
    "output_language": "auto"
  }'
```

Poll `GET /api/v1/jobs/{id}`. Stages are `queued`, `downloading`,
`transcribing`, `generating`, `archiving`, `completed`, and `failed`.

## Google Drive evidence archive on DGX Spark

Every successful job is written first to `/data/drive-outbox` as both JSON and
Markdown. Each pair contains the source URL and video metadata, the request,
the complete transcript, and every generated question, answer, and exact
evidence quote. A temporary Google Drive outage therefore cannot discard a
completed knowledge set.

The optional `drive-sync` service copies that durable outbox to the existing
`knowledge-drive:AnswersFromYoutubeVideos` rclone destination:

```bash
docker compose --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.spark.yml \
  --profile drive up -d drive-sync
```

Set `RCLONE_CONFIG_PATH`, `DRIVE_REMOTE`, `DRIVE_FOLDER`, and
`DRIVE_SYNC_INTERVAL` in `.env`; see `.env.spark.example`. The rclone config is
mounted read-only and is never copied into the repository or image.

If a job fails during question grounding after its transcript was saved, retry
only the LLM stage with `POST /api/v1/jobs/{id}/retry-generation`. The API
reuses the stored transcript and does not download or transcribe the video again.

## Deployment

- Set the Vercel project root to `apps/web`.
- Run the API container on Spark with a persistent `/data` volume. Its default
  host port is `8020`, separate from the existing Research Knowledge API.
- Publish the API through Cloudflare Tunnel; see
  [`deploy/cloudflare/README.md`](deploy/cloudflare/README.md).
- Set an exact `CORS_ORIGINS` allowlist on the API.
- Apply an edge rate limit to `POST /api/v1/jobs` before making the app public.
- Keep all model and transcription keys on Spark, never in Vercel.

## Development

```bash
make test
```

CI runs Ruff and Pytest for the API, then TypeScript and a production Next.js
build for the web app.

## Responsible use

Only process videos you are authorized to access. Youtube2knowledge does not
bypass private videos, DRM, age restrictions, or platform access controls.
Review YouTube's terms and applicable copyright rules for your use case.

## License

[MIT](LICENSE)
