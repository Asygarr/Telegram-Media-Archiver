"""Skrip sekali-jalan untuk mengekspor session string tgdl.

Jalankan:
    python scripts/export_session.py

Pyrogram akan meminta nomor telepon, OTP, dan (bila aktif) password 2FA secara
interaktif. Salin output SESSION_STRING ke `.env` — JANGAN commit.
"""

from __future__ import annotations

import asyncio

from tgdl.auth import export_session_string
from tgdl.config import load_settings


async def _main() -> None:
    settings = load_settings()
    session = await export_session_string(settings)
    print("\n" + "=" * 60)
    print("SESSION_STRING (simpan ke .env, JANGAN commit / bagikan):")
    print("=" * 60)
    print(session)
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(_main())
