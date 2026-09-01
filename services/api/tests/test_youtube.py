import subprocess
from pathlib import Path

import pytest

from app.youtube import YouTubeError, download_audio, extract_video_id


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=20", "dQw4w9WgXcQ"),
        ("https://youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_extract_video_id(url: str, expected: str) -> None:
    assert extract_video_id(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/playlist?list=PL123",
        "https://youtube.com/watch?v=bad$id",
    ],
)
def test_rejects_unsupported_urls(url: str) -> None:
    with pytest.raises(YouTubeError):
        extract_video_id(url)


def test_download_audio_normalizes_to_nim_compatible_wav(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    yt_dlp_arguments: list[str] = []
    ffmpeg_command: list[str] = []

    def fake_yt_dlp(arguments: list[str], timeout: int):
        yt_dlp_arguments.extend(arguments)
        (tmp_path / "source.webm").write_bytes(b"source")
        return subprocess.CompletedProcess(arguments, 0, "", "")

    def fake_ffmpeg(command: list[str], **kwargs):
        ffmpeg_command.extend(command)
        (tmp_path / "audio.wav").write_bytes(b"wav")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.youtube._run_yt_dlp", fake_yt_dlp)
    monkeypatch.setattr("app.youtube.subprocess.run", fake_ffmpeg)

    result = download_audio("https://youtu.be/dQw4w9WgXcQ", tmp_path)

    assert result == tmp_path / "audio.wav"
    assert "bestaudio/best" in yt_dlp_arguments
    assert ffmpeg_command[ffmpeg_command.index("-ac") + 1] == "1"
    assert ffmpeg_command[ffmpeg_command.index("-ar") + 1] == "16000"
    assert ffmpeg_command[ffmpeg_command.index("-c:a") + 1] == "pcm_s16le"
