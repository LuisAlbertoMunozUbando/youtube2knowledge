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


def inspect_video(url: str, max_minutes: int) -> VideoMetadata:
    extract_video_id(url)
    result = _run_yt_dlp(["--dump-single-json", "--skip-download", url], timeout=60)
    raw = json.loads(result.stdout)
    duration = int(raw.get("duration") or 0) or None
    if duration and duration > max_minutes * 60:
        raise YouTubeError(f"Video exceeds the {max_minutes}-minute limit")
    return VideoMetadata(
        video_id=str(raw.get("id") or extract_video_id(url)),
        title=str(raw.get("title") or "Untitled video"),
        channel=raw.get("channel") or raw.get("uploader"),
        duration_seconds=duration,
        thumbnail_url=raw.get("thumbnail"),
    )


def download_audio(url: str, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    output_template = str(destination / "audio.%(ext)s")
    _run_yt_dlp(
        [
            "-f",
            "bestaudio/best",
            "-x",
            "--audio-format",
            "flac",
            "--audio-quality",
            "5",
            "-o",
            output_template,
            url,
        ],
        timeout=1800,
    )
    audio_path = destination / "audio.flac"
    if not audio_path.is_file() or audio_path.stat().st_size == 0:
        raise YouTubeError("Audio extraction produced no file")
    return audio_path
