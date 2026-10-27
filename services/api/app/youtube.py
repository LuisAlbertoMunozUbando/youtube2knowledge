import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .models import VideoMetadata

ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


class YouTubeError(RuntimeError):
    pass


def extract_video_id(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise YouTubeError("Only youtube.com and youtu.be URLs are accepted")

    if host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    elif parsed.path.startswith("/shorts/") or parsed.path.startswith("/embed/"):
        video_id = parsed.path.split("/")[2]
    else:
        raise YouTubeError("The URL does not identify a single YouTube video")

    if not video_id or len(video_id) > 32 or not all(c.isalnum() or c in "-_" for c in video_id):
        raise YouTubeError("Invalid YouTube video ID")
    return video_id


def _run_yt_dlp(arguments: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "yt_dlp", "--no-playlist", *arguments]
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise YouTubeError("YouTube operation timed out") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "yt-dlp failed").strip().splitlines()[-1]
        raise YouTubeError(detail) from exc


def inspect_video(url: str, max_minutes: int, start_seconds: int = 0, end_seconds: int | None = None) -> VideoMetadata:
    extract_video_id(url)
    result = _run_yt_dlp(["--dump-single-json", "--skip-download", url], timeout=60)
    raw = json.loads(result.stdout)
    duration = int(raw.get("duration") or 0) or None
    if start_seconds < 0 or (end_seconds is not None and end_seconds <= start_seconds):
        raise YouTubeError("Invalid selected interval")
    if end_seconds is None:
        if start_seconds != 0:
            raise YouTubeError("An end time is required when selecting a start time")
        if duration and duration > max_minutes * 60:
            raise YouTubeError(f"Select an interval of at most {max_minutes} minutes")
    elif end_seconds - start_seconds > max_minutes * 60:
        raise YouTubeError(f"Selected interval exceeds {max_minutes} minutes")
    if duration is not None and (start_seconds >= duration or (end_seconds is not None and end_seconds > duration)):
        raise YouTubeError("Selected interval is outside the video duration")
    return VideoMetadata(
        video_id=str(raw.get("id") or extract_video_id(url)),
        title=str(raw.get("title") or "Untitled video"),
        channel=raw.get("channel") or raw.get("uploader"),
        duration_seconds=duration,
        thumbnail_url=raw.get("thumbnail"),
    )


def download_audio(url: str, destination: Path, start_seconds: int = 0, end_seconds: int | None = None) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    output_template = str(destination / "source.%(ext)s")
    download_args = [
            "-f",
            "bestaudio/best",
            "-o",
            output_template,
            url,
        ]
    if end_seconds is not None:
        download_args = ["--download-sections", f"*{start_seconds}-{end_seconds}", "--force-keyframes-at-cuts", *download_args]
    _run_yt_dlp(download_args, timeout=1800)
    sources = sorted(
        path
        for path in destination.glob("source.*")
        if path.is_file() and path.suffix != ".part"
    )
    if len(sources) != 1:
        raise YouTubeError("Audio download produced an unexpected file set")

    audio_path = destination / "audio.wav"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(sources[0]),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(audio_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise YouTubeError("Audio normalization to WAV failed") from exc

    if not audio_path.is_file() or audio_path.stat().st_size == 0:
        raise YouTubeError("Audio extraction produced no file")
    return audio_path
