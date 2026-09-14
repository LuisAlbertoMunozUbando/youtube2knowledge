import subprocess
from pathlib import Path

import httpx

from ..config import Settings


class TranscriptionError(RuntimeError):
    pass


def _response_error(service: str, response: httpx.Response) -> TranscriptionError:
    detail = response.text.strip().replace("\n", " ")[:500]
    suffix = f": {detail}" if detail else ""
    return TranscriptionError(f"{service} returned {response.status_code}{suffix}")


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
                files={"file": (chunk.name, audio_file, "audio/wav")},
                timeout=1800,
            )
        if response.is_error:
            raise _response_error("Transcription API", response)
        text = str(response.json().get("text") or "").strip()
        if text:
            transcripts.append(text)
    transcript = "\n\n".join(transcripts)
    if not transcript:
        raise TranscriptionError("Transcription API returned an empty transcript")
    return transcript


def _nim_transcribe_file(
    audio_path: Path,
    settings: Settings,
    language_code: str,
) -> str:
    """Send one normalized WAV file to NVIDIA Speech NIM."""
    data: dict[str, str] = {
        "enable_automatic_punctuation": "true",
        "language": language_code,
    }
    headers = {}
    if settings.transcription_api_key:
        headers["Authorization"] = f"Bearer {settings.transcription_api_key}"
    with audio_path.open("rb") as audio_file:
        response = httpx.post(
            f"{settings.transcription_api_base_url.rstrip('/')}/audio/transcriptions",
            headers=headers,
            data=data,
            files={"file": (audio_path.name, audio_file, "audio/wav")},
            timeout=1800,
        )
    if response.is_error:
        raise _response_error("NVIDIA Speech NIM", response)
    return str(response.json().get("text") or "").strip()


def _transcribe_nvidia_nim(audio_path: Path, settings: Settings, language: str) -> str:
    """Transcribe through NVIDIA Speech NIM with a sparse-speech fallback.

    The normal path is intentionally unchanged: first try the existing size-based
    chunks.  Only when that entire first pass returns no text do we perform an
    exhaustive second pass using short, overlapping windows.  This catches videos
    with long silent/music sections and only brief islands of speech without
    penalizing normal videos.
    """
    language_codes = {"auto": "multi", "en": "en-US", "es": "es-ES"}
    language_code = language_codes.get(language, "multi")

    transcripts: list[str] = []
    for chunk in _audio_chunks(audio_path):
        text = _nim_transcribe_file(chunk, settings, language_code)
        if text:
            transcripts.append(text)

    transcript = "\n\n".join(transcripts).strip()
    if transcript:
        return transcript

    # Fallback: no speech at all was found during the normal pass.  Search the
    # entire recording with 10-second windows advancing every 5 seconds.  The
    # overlap prevents short phrases from being lost at segment boundaries.
    fallback_texts: list[str] = []
    for window in _audio_windows(audio_path, window_seconds=10.0, step_seconds=5.0):
        text = _nim_transcribe_file(window, settings, language_code)
        if text:
            fallback_texts.append(text)

    transcript = _merge_overlapping_transcripts(fallback_texts)
    if not transcript:
        raise TranscriptionError("NVIDIA Speech NIM returned an empty transcript")
    return transcript


def _probe_audio_duration(audio_path: Path) -> float:
    """Return audio duration in seconds using ffprobe."""
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        duration = float(completed.stdout.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
        raise TranscriptionError("Unable to determine audio duration") from exc
    if duration <= 0:
        raise TranscriptionError("Audio duration is invalid")
    return duration


def _audio_windows(
    audio_path: Path,
    window_seconds: float = 10.0,
    step_seconds: float = 5.0,
) -> list[Path]:
    """Create short overlapping PCM WAV windows for exhaustive ASR scanning."""
    if window_seconds <= 0 or step_seconds <= 0:
        raise ValueError("window_seconds and step_seconds must be positive")

    duration = _probe_audio_duration(audio_path)
    window_dir = audio_path.parent / "nim-fallback-windows"
    window_dir.mkdir(exist_ok=True)

    # Clear stale windows if a work directory is ever reused.
    for stale in window_dir.glob("window-*.wav"):
        stale.unlink(missing_ok=True)

    windows: list[Path] = []
    start = 0.0
    index = 0
    while start < duration:
        output = window_dir / f"window-{index:04d}-{int(start):06d}ms.wav"
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    f"{start:.3f}",
                    "-i",
                    str(audio_path),
                    "-t",
                    f"{window_seconds:.3f}",
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise TranscriptionError("Unable to create fallback ASR windows") from exc
        if output.is_file() and output.stat().st_size > 44:
            windows.append(output)
        index += 1
        start += step_seconds

    if not windows:
        raise TranscriptionError("Fallback ASR windowing produced no audio")
    return windows


def _merge_overlapping_transcripts(transcripts: list[str]) -> str:
    """Merge overlapping ASR windows while removing obvious repeated word runs."""
    cleaned = [text.strip() for text in transcripts if text and text.strip()]
    if not cleaned:
        return ""

    merged_words = cleaned[0].split()
    for text in cleaned[1:]:
        words = text.split()
        if not words:
            continue

        max_overlap = min(len(merged_words), len(words), 30)
        overlap = 0
        for size in range(max_overlap, 0, -1):
            left = [w.casefold().strip(".,;:!?¡¿\"'") for w in merged_words[-size:]]
            right = [w.casefold().strip(".,;:!?¡¿\"'") for w in words[:size]]
            if left == right:
                overlap = size
                break
        merged_words.extend(words[overlap:])

    return " ".join(merged_words).strip()


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
