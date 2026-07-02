"""Konfigurasi aplikasi tgdl.

Memuat pengaturan dari environment/`.env` menggunakan pydantic-settings.
Tidak ada nilai rahasia yang di-hardcode; kredensial hanya berasal dari environment.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Pengaturan runtime tgdl yang divalidasi.

    Semua field dibaca dari environment variable (atau file `.env`).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Kredensial dari my.telegram.org (WAJIB)
    api_id: int = Field(..., alias="API_ID")
    api_hash: str = Field(..., alias="API_HASH")

    # Opsional
    phone_number: str | None = Field(default=None, alias="PHONE_NUMBER")
    session_string: str | None = Field(default=None, alias="SESSION_STRING")

    # Perilaku unduhan
    download_dir: Path = Field(default=Path("downloads"), alias="DOWNLOAD_DIR")
    concurrency: int = Field(default=3, alias="CONCURRENCY", ge=1, le=16)
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("api_hash")
    @classmethod
    def _api_hash_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("API_HASH tidak boleh kosong")
        return value.strip()

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL harus salah satu dari {sorted(allowed)}")
        return upper


def load_settings() -> Settings:
    """Muat dan validasi pengaturan dari environment/`.env`."""
    return Settings()  # type: ignore[call-arg]
