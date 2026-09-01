# Architecture notes

## Boundaries

The browser owns user configuration and rendering. It never receives provider
credentials. The API owns URL validation, media work, model calls, job state,
and cleanup.

## Job lifecycle

`POST /api/v1/jobs` validates the host and creates a random job identifier. A
background task then advances through these persisted stages:

```text
queued → downloading → transcribing → generating → completed
                                              └──→ failed
```

Job writes use a temporary file followed by an atomic rename. Work audio is
deleted after success or failure. The final transcript and Q&A remain in the
job record.

This first release intentionally runs one Uvicorn worker. In-memory concurrency
control does not coordinate across processes. A later horizontally scaled
release should replace background tasks and JSON state with a durable queue and
database.

## Trust model

- Only `youtube.com` and `youtu.be` hosts are accepted.
- Only one video is accepted; playlists are disabled.
- `yt-dlp` never receives arbitrary command-line options from the client.
- CORS uses explicit origins.
- Generated answers must contain transcript evidence.
- API keys exist only in the Spark environment.

Before public launch, Cloudflare must rate-limit job creation. For multi-user
or high-cost operation, add Turnstile or authenticated quotas in front of the
create-job endpoint.

## Provider interfaces

Transcription is selected by `TRANSCRIPTION_PROVIDER`:

- `openai`: HTTP multipart transcription; audio larger than 20 MB is segmented.
- `local_whisper`: `faster-whisper`, configured by model, device, and compute
  type.

Question generation calls `/chat/completions`. It first requests JSON mode and
retries without `response_format` when a compatible provider does not implement
that option. The returned shape is validated before it reaches the browser.
