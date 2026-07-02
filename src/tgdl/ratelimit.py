"""Penanganan rate limit & error transien Telegram untuk tgdl.

Menyediakan:
- ``with_floodwait``: tunggu + retry saat ``FloodWait``.
- ``with_retry``: backoff eksponensial untuk error transien jaringan.
- ``safe_download``: unduh dengan pemulihan otomatis saat ``FileReferenceExpired``.

Aturan: hormati FloodWait sepenuhnya; jangan pernah mencatat kredensial.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pyrogram import Client
from pyrogram.errors import FileReferenceExpired, FloodWait
from pyrogram.types import Message

log = logging.getLogger("tgdl.ratelimit")

T = TypeVar("T")

# Error transien yang layak di-retry dengan backoff.
TRANSIENT: tuple[type[Exception], ...] = (ConnectionError, TimeoutError, OSError)


async def with_floodwait(
    coro_factory: Callable[[], Awaitable[T]],
    max_retries: int = 5,
) -> T:
    """Jalankan coroutine dan tangani ``FloodWait`` dengan menunggu lalu retry.

    Args:
        coro_factory: Fungsi tanpa argumen yang mengembalikan coroutine baru
            setiap dipanggil (agar bisa dijalankan ulang saat retry).
        max_retries: Batas percobaan ulang saat terkena FloodWait.

    Returns:
        Hasil coroutine bila sukses.

    Raises:
        FloodWait: Bila melewati ``max_retries``.
    """
    attempt = 0
    while True:
        try:
            return await coro_factory()
        except FloodWait as exc:
            attempt += 1
            if attempt > max_retries:
                raise
            wait = int(getattr(exc, "value", 5) or 5) + 1
            log.warning("FloodWait: menunggu %ss (percobaan %d/%d)", wait, attempt, max_retries)
            await asyncio.sleep(wait)


async def with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    retries: int = 3,
    base: float = 2.0,
) -> T:
    """Jalankan coroutine dengan backoff eksponensial untuk error transien.

    Args:
        coro_factory: Fungsi yang mengembalikan coroutine baru tiap dipanggil.
        retries: Jumlah percobaan total.
        base: Basis backoff (delay = ``base ** i`` detik).

    Raises:
        Exception: Error terakhir bila semua percobaan gagal.
    """
    last_exc: Exception | None = None
    for i in range(retries):
        try:
            return await coro_factory()
        except TRANSIENT as exc:
            last_exc = exc
            if i == retries - 1:
                break
            delay = base**i
            log.warning("Error transien: %s — retry dalam %.1fs", exc, delay)
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


async def safe_download(
    client: Client,
    message: Message,
    file_name: str,
    progress: Callable[[int, int], None] | None = None,
) -> str | None:
    """Unduh media dengan penanganan ``FloodWait`` dan ``FileReferenceExpired``.

    Bila referensi file kedaluwarsa, pesan diambil ulang (``get_messages``) lalu
    unduhan dicoba kembali.
    """

    def _download(msg: Message) -> Awaitable[str | None]:
        return client.download_media(msg, file_name=file_name, progress=progress)

    try:
        return await with_floodwait(lambda: _download(message))
    except FileReferenceExpired:
        log.warning("FileReferenceExpired pada pesan %s — mengambil ulang", message.id)
        fresh = await client.get_messages(message.chat.id, message.id)
        return await with_floodwait(lambda: _download(fresh))
