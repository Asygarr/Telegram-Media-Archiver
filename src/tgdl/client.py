"""Lifecycle & pembuatan Pyrogram client untuk tgdl.

Membuat client dari session string (mode in-memory) atau login interaktif.
Session string diperlakukan sebagai rahasia: tidak pernah di-log/print di alur normal.
"""

from __future__ import annotations

from pyrogram import Client

from .config import Settings

_CLIENT_NAME = "tgdl"


def build_client(settings: Settings) -> Client:
    """Bangun Pyrogram client sesuai konfigurasi.

    - Jika ``session_string`` tersedia: gunakan mode ``in_memory`` (tidak menulis file
      ``.session`` ke disk).
    - Jika tidak: siapkan login interaktif berbasis nomor telepon (menghasilkan file
      session lokal yang sudah masuk ``.gitignore``).
    """
    if settings.session_string:
        return Client(
            name=_CLIENT_NAME,
            api_id=settings.api_id,
            api_hash=settings.api_hash,
            session_string=settings.session_string,
            in_memory=True,
        )

    return Client(
        name=_CLIENT_NAME,
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        phone_number=settings.phone_number,
    )
