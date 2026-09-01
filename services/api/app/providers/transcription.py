import subprocess
from pathlib import Path

import httpx

from ..config import Settings


class TranscriptionError(RuntimeError):
    pass


def transcribe(audio_path: Path, settings: Settings, language: str = "auto") -> str:
    if settings.transcription_provider == "openai":
        return _transcribe_openai(audio_path, settings, language)
    if settings.transcription_provider == "nvidia_nim":
        return _transcribe_nvidia_nim(audio_path, settings, language)
    return _transcribe_local(audio_path, settings, language)


def _transcribe_openai(audio_path: Path, settings: Settings, language: str) -> str:
    if not settings.transcription_api_key:
        raise TranscriptionError("TRANSCRIPTION_API_KEY is required for the openai provider")
    chunks = _audio_chunks(audio_path)
    transcripts: list[str] = []
    for chunk in chunks:
        data = {"model": settings.transcription_model, "response_format": "json"}
        if language != "auto":
            data["language"] = language
        headers = {"Authorization": f"Bearer {settings.transcription_api_key}"}
        with chunk.open("rb") as audio_file:
            response = httpx.post(
                f"{settings.transcription_api_base_url.rstrip('/')}/audio/transcriptions",
                headers=headers,
                data=data,
                files={"file": (chunk.name, audio_file, "audio/mpeg")},
                timeout=1800,
            )
        if response.is_error:
            raise TranscriptionError(f"Transcription API returned {response.status_code}")
        text = str(response.json().get("text") or "").strip()
        if text:
            transcripts.append(text)
    transcript = "\n\n".join(transcripts)
    if not transcript:
        raise TranscriptionError("Transcription API returned an empty transcript")
    return transcript


def _transcribe_nvidia_nim(audio_path: Path, settings: Settings, language: str) -> str:
    """Transcribe through the NVIDIA Speech NIM offline HTTP endpoint."""
    language_codes = {"auto": "multi", "en": "en-US", "es": "es-ES"}
    chunks = _audio_chunks(audio_path)
    transcripts: list[str] = []
    for chunk in chunks:
        data: dict[str, str] = {
            "enable_automatic_punctuation": "true",
            "language": language_codes.get(language, "multi"),
        }
        headers = {}
        if settings.transcription_api_key:
            headers["Authorization"] = f"Bearer {settings.transcription_api_key}"
        with chunk.open("rb") as audio_file:
            response = httpx.post(
                f"{settings.transcription_api_base_url.rstrip('/')}/audio/transcriptions",
                headers=headers,
                data=data,
                files={"file": (chunk.name, audio_file, "audio/flac")},
                timeout=1800,
            )
        if response.is_error:
            raise TranscriptionError(f"NVIDIA Speech NIM returned {response.status_code}")
        text = str(response.json().get("text") or "").strip()
        if text:
            transcripts.append(text)
    transcript = "\n\n".join(transcripts)
    if not transcript:
        raise TranscriptionError("NVIDIA Speech NIM returned an empty transcript")
    return transcript


def _audio_chunks(audio_path: Path) -> list[Path]:
    """Keep every upload safely below the common 25 MB transcription limit."""
    if audio_path.stat().st_size < 20 * 1024 * 1024:
        return [audio_path]
    chunk_dir = audio_path.parent / "chunks"
    chunk_dir.mkdir(exist_ok=True)
    output = chunk_dir / f"chunk-%03d{audio_path.suffix}"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(audio_path),
                "-f",
                "segment",
                "-segment_time",
                "600",
                "-c",
                "copy",
                str(output),
            ],
            check=True,
            timeout=600,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise TranscriptionError("Unable to split audio for transcription") from exc
    chunks = sorted(chunk_dir.glob(f"chunk-*{audio_path.suffix}"))
    if not chunks:
        raise TranscriptionError("Audio splitting produced no chunks")
    return chunks


def _transcribe_local(audio_path: Path, settings: Settings, language: str) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(
            "Install the local-whisper extra or use TRANSCRIPTION_PROVIDER=openai"
        ) from exc

    model = WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )
    segments, _ = model.transcribe(
        str(audio_path),
        language=None if language == "auto" else language,
        vad_filter=True,
    )
    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    if not text:
        raise TranscriptionError("Local Whisper returned an empty transcript")
    return text
