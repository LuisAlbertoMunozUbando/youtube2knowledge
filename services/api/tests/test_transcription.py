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


def test_nvidia_nim_falls_back_to_overlapping_windows_when_first_pass_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    window1 = tmp_path / "window-0000.wav"
    window2 = tmp_path / "window-0001.wav"
    window1.write_bytes(b"window1")
    window2.write_bytes(b"window2")

    calls: list[str] = []

    def fake_transcribe_file(path, settings, language_code):
        calls.append(path.name)
        return {
            "audio.wav": "",
            "window-0000.wav": "Esta es una voz breve",
            "window-0001.wav": "voz breve encontrada",
        }.get(path.name, "")

    monkeypatch.setattr(
        "app.providers.transcription._nim_transcribe_file",
        fake_transcribe_file,
    )
    monkeypatch.setattr(
        "app.providers.transcription._audio_windows",
        lambda *args, **kwargs: [window1, window2],
    )

    settings = Settings(
        transcription_provider="nvidia_nim",
        transcription_api_base_url="http://asr:9000/v1",
    )

    result = _transcribe_nvidia_nim(audio, settings, "es")

    assert result == "Esta es una voz breve encontrada"
    assert calls == ["audio.wav", "window-0000.wav", "window-0001.wav"]


def test_nvidia_nim_does_not_run_fallback_when_first_pass_has_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")

    monkeypatch.setattr(
        "app.providers.transcription._nim_transcribe_file",
        lambda *args, **kwargs: "Texto encontrado normalmente",
    )

    def unexpected_fallback(*args, **kwargs):
        raise AssertionError("fallback should not run")

    monkeypatch.setattr(
        "app.providers.transcription._audio_windows",
        unexpected_fallback,
    )

    settings = Settings(
        transcription_provider="nvidia_nim",
        transcription_api_base_url="http://asr:9000/v1",
    )

    assert _transcribe_nvidia_nim(audio, settings, "es") == "Texto encontrado normalmente"


def test_transcription_error_preserves_response_detail() -> None:
    response = FakeResponse()
    response.is_error = True
    response.status_code = 400
    response.text = '{"detail":"Only WAV audio is accepted"}'

    error = _response_error("NVIDIA Speech NIM", response)

    assert str(error) == (
        'NVIDIA Speech NIM returned 400: {"detail":"Only WAV audio is accepted"}'
    )
