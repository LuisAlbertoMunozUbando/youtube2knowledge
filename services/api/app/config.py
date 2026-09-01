from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_data_dir: Path = Path("./data")
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    max_video_minutes: int = 180
    max_concurrent_jobs: int = 1

    transcription_provider: str = "openai"
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "int8"
    transcription_api_base_url: str = "https://api.openai.com/v1"
    transcription_api_key: str = ""
    transcription_model: str = "whisper-1"

    llm_api_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: int = 180
    llm_max_tokens: int = 4096

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("transcription_provider")
    @classmethod
    def supported_transcriber(cls, value: str) -> str:
        if value not in {"local_whisper", "nvidia_nim", "openai"}:
            raise ValueError(
                "TRANSCRIPTION_PROVIDER must be local_whisper, nvidia_nim, or openai"
            )
        return value

    @property
    def jobs_dir(self) -> Path:
        return self.app_data_dir / "jobs"

    @property
    def work_dir(self) -> Path:
        return self.app_data_dir / "work"

    @property
    def drive_outbox_dir(self) -> Path:
        return self.app_data_dir / "drive-outbox"


@lru_cache
def get_settings() -> Settings:
    return Settings()
