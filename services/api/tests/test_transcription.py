from pathlib import Path

from app.config import Settings
from app.providers.transcription import (
    _response_error,
    _transcribe_nvidia_nim,
)


class FakeResponse:
    is_error = False
    status_code = 200
    text = ""

    def json(self) -> dict[str, str]:
        return {"text": "Local NVIDIA transcript"}


def test_nvidia_nim_transcription_requires_no_api_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("app.providers.transcription.httpx.post", fake_post)
    settings = Settings(
        transcription_provider="nvidia_nim",
        transcription_api_base_url="http://asr:9000/v1",
        transcription_api_key="",
    )

    result = _transcribe_nvidia_nim(audio, settings, "auto")

    assert result == "Local NVIDIA transcript"
    assert captured["url"] == "http://asr:9000/v1/audio/transcriptions"
    assert captured["headers"] == {}
    assert captured["data"] == {
        "enable_automatic_punctuation": "true",
        "language": "multi",
    }
    assert captured["files"]["file"][2] == "audio/wav"


def test_nvidia_nim_maps_spanish_language(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("app.providers.transcription.httpx.post", fake_post)
    settings = Settings(
        transcription_provider="nvidia_nim",
        transcription_api_base_url="http://asr:9000/v1",
    )

    _transcribe_nvidia_nim(audio, settings, "es")

    assert captured["data"] == {
        "enable_automatic_punctuation": "true",
        "language": "es-ES",
    }


def test_transcription_error_preserves_response_detail() -> None:
    response = FakeResponse()
    response.is_error = True
    response.status_code = 400
    response.text = '{"detail":"Only WAV audio is accepted"}'

    error = _response_error("NVIDIA Speech NIM", response)

    assert str(error) == (
        'NVIDIA Speech NIM returned 400: {"detail":"Only WAV audio is accepted"}'
    )
