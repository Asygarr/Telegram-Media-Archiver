"""Penemuan & filter pesan bermedia pada sebuah chat.

Menyediakan iterasi asinkron atas riwayat pesan dengan filter tipe media,
rentang id, rentang tanggal, dan substring caption, sesuai kontrak arsitektur
(Fase 03).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, time

from pyrogram import Client
from pyrogram.enums import MessageMediaType
from pyrogram.types import Message

# Peta nama tipe (untuk CLI) -> enum Pyrogram
MEDIA_TYPES: dict[str, MessageMediaType] = {
    "photo": MessageMediaType.PHOTO,
    "video": MessageMediaType.VIDEO,
    "document": MessageMediaType.DOCUMENT,
    "audio": MessageMediaType.AUDIO,
    "voice": MessageMediaType.VOICE,
    "video_note": MessageMediaType.VIDEO_NOTE,
    "animation": MessageMediaType.ANIMATION,
    "sticker": MessageMediaType.STICKER,
}


def normalize_chat(chat: str | int) -> str | int:
    """Normalisasi target chat.

    ID numerik (mis. ``"-1001234567890"``) dikonversi ke ``int`` agar Pyrogram
    tidak salah menafsirkannya sebagai nomor telepon (``contacts.ResolvePhone``).
    Username/link dibiarkan sebagai string.
    """
    if isinstance(chat, int):
        return chat
    s = chat.strip()
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s



def parse_types(spec: str | None) -> set[MessageMediaType] | None:
    """Ubah string ``"photo,video"`` menjadi himpunan enum tipe media.

    Mengembalikan ``None`` bila ``spec`` kosong (artinya semua tipe diterima).
    """
    if not spec:
        return None
    result: set[MessageMediaType] = set()
    for raw in spec.split(","):
        key = raw.strip().lower()
        if not key:
            continue
        if key not in MEDIA_TYPES:
            valid = ", ".join(sorted(MEDIA_TYPES))
            raise ValueError(f"Tipe media tidak dikenal: {key!r}. Pilihan: {valid}")
        result.add(MEDIA_TYPES[key])
    return result or None


def get_media_object(message: Message) -> object | None:
    """Kembalikan objek media pada pesan (foto/video/dll) atau ``None``."""
    return (
        message.photo
        or message.video
        or message.document
        or message.audio
        or message.voice
        or message.video_note
        or message.animation
        or message.sticker
    )


def get_file_unique_id(message: Message) -> str | None:
    """Ambil ``file_unique_id`` media pada pesan untuk keperluan dedup."""
    media = get_media_object(message)
    return getattr(media, "file_unique_id", None) if media is not None else None


def get_thumb_file_id(message: Message) -> str | None:
    """Ambil ``file_id`` thumbnail terkecil pada pesan, bila tersedia.

    Urutan: thumbnail terkecil (``media.thumbs[0]``) -> file_id foto itu sendiri
    -> ``None`` (mis. voice/audio/dokumen tanpa thumbnail).
    """
    media = get_media_object(message)
    thumbs = getattr(media, "thumbs", None)
    if thumbs:
        return getattr(thumbs[0], "file_id", None)
    if message.photo is not None:
        return getattr(message.photo, "file_id", None)
    return None


def parse_date(spec: str, end_of_day: bool = False) -> datetime:
    """Ubah string tanggal/waktu menjadi ``datetime`` sadar-zona (UTC).

    Menerima ``"YYYY-MM-DD"``, ``"YYYY-MM-DD HH:MM[:SS]"``, atau ISO 8601 penuh
    (termasuk offset zona waktu). Bila hanya tanggal yang diberikan (tanpa
    komponen waktu) dan ``end_of_day=True``, waktu diisi akhir hari
    (``23:59:59.999999``) alih-alih awal hari — berguna untuk filter ``--until``
    agar tanggal akhir ikut tercakup penuh.

    Raises:
        ValueError: Bila format tidak dapat diparse.
    """
    s = spec.strip()
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(
            f"Format tanggal tidak valid: {spec!r}. Gunakan YYYY-MM-DD atau ISO 8601."
        ) from exc
    date_only = "T" not in s and " " not in s
    if date_only and end_of_day:
        dt = datetime.combine(dt.date(), time(23, 59, 59, 999999))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


async def iter_media_messages(
    client: Client,
    chat: str | int,
    types: set[MessageMediaType] | None = None,
    limit: int = 0,
    min_id: int = 0,
    max_id: int = 0,
    since: datetime | None = None,
    until: datetime | None = None,
    caption_contains: str | None = None,
) -> AsyncIterator[Message]:
    """Iterasi pesan bermedia pada ``chat`` dengan filter opsional.

    Args:
        client: Pyrogram client aktif.
        chat: Username, ID numerik, atau link chat target.
        types: Himpunan tipe media yang diterima (``None`` = semua).
        limit: Batas jumlah pesan yang dipindai (0 = tanpa batas).
        min_id: Hanya pesan dengan ``id`` > ``min_id`` (0 = abaikan).
        max_id: Mulai dari ``id`` ini ke bawah (0 = dari terbaru).
        since: Hanya pesan dengan ``date`` >= ``since`` (``None`` = abaikan).
        until: Hanya pesan dengan ``date`` <= ``until`` (``None`` = abaikan).
        caption_contains: Substring (case-insensitive) yang harus ada pada
            caption pesan (``None`` = abaikan).

    Yields:
        Pesan yang memiliki media dan lolos seluruh filter.
    """
    needle = caption_contains.lower() if caption_contains else None
    async for message in client.get_chat_history(
        chat, limit=limit, max_id=max_id, min_id=min_id
    ):
        if min_id and message.id <= min_id:
            break
        if message.media is None:
            continue
        if types is not None and message.media not in types:
            continue
        if message.date is not None:
            # Riwayat diiterasi dari terbaru ke terlama: setelah melewati batas
            # bawah (`since`) tidak ada lagi pesan yang lolos, aman untuk henti.
            if since is not None and message.date < since:
                break
            if until is not None and message.date > until:
                continue
        if needle is not None and needle not in (message.caption or "").lower():
            continue
        yield message
