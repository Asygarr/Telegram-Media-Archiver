"""Autentikasi & manajemen session untuk tgdl.

Menyediakan helper untuk mengekspor session string (login pertama, termasuk 2FA)
tanpa membocorkan kredensial. Session string setara kredensial penuh akun.
"""

from __future__ import annotations

import logging

from pyrogram import Client

from .config import Settings

log = logging.getLogger("tgdl.auth")


async def export_session_string(settings: Settings) -> str:
    """Login interaktif lalu kembalikan session string.

    Pyrogram meminta nomor telepon, kode OTP, dan (bila aktif) password 2FA secara
    interaktif melalui terminal. Nilai OTP/2FA tidak pernah dicatat ke log.

    Returns:
        Session string yang harus disimpan sebagai rahasia (mis. ``SESSION_STRING``
        di ``.env``). Jangan commit atau bagikan.
    """
    async with Client(
        name="tgdl_login",
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        phone_number=settings.phone_number,
        in_memory=True,
    ) as app:
        me = await app.get_me()
        log.info("Login berhasil sebagai user id=%s", me.id)
        session = await app.export_session_string()
        return str(session)
