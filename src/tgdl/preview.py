"""Pengumpulan item media untuk halaman preview (gallery).

Memindai riwayat chat sekali, membangun metadata ringan per media untuk
ditampilkan di gallery, dan menyimpan objek ``Message`` dalam cache agar bisa
dipakai ulang saat unduhan dipicu dari UI (tanpa memindai ulang).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pyrogram import Client
from pyrogram.enums import MessageMediaType
from pyrogram.types import Chat, Message

from . import discovery
from .discovery import get_media_object, get_thumb_file_id
from .storage import media_kind


@dataclass
class ChatInfo:
    """Ringkasan chat untuk header gallery."""

    id: int
    title: str
    username: str | None


@dataclass
class PreviewResult:
    """Hasil pemindaian preview: metadata item + cache pesan."""

    chat: ChatInfo
    items: list[dict[str, object]] = field(default_factory=list)
    messages: dict[int, Message] = field(default_factory=dict)


def _media_metadata(message: Message) -> dict[str, object]:
    """Ekstrak metadata ringan dari media sebuah pesan untuk ditampilkan."""
    media = get_media_object(message)
    return {
        "message_id": message.id,
        "type": media_kind(message),
        "size": getattr(media, "file_size", None),
        "width": getattr(media, "width", None),
        "height": getattr(media, "height", None),
        "duration": getattr(media, "duration", None),
        "file_name": getattr(media, "file_name", None),
        "caption": message.caption or "",
        "date": message.date.isoformat() if message.date else None,
        "has_thumb": get_thumb_file_id(message) is not None,
    }


def _chat_info(chat: Chat) -> ChatInfo:
    title = chat.title or chat.username or chat.first_name or f"id{chat.id}"
    return ChatInfo(id=chat.id or 0, title=str(title), username=chat.username)


async def collect_items(
    client: Client,
    chat: str | int,
    types: set[MessageMediaType] | None = None,
    limit: int = 0,
    min_id: int = 0,
    max_id: int = 0,
    since: datetime | None = None,
    until: datetime | None = None,
    caption_contains: str | None = None,
) -> PreviewResult:
    """Pindai media pada ``chat`` dan bangun metadata + cache pesan untuk preview.

    Args mengikuti ``discovery.iter_media_messages``. Objek ``Message`` disimpan
    dalam ``PreviewResult.messages`` keyed oleh ``message_id`` untuk dipakai ulang
    ketika unduhan dipicu dari UI gallery.
    """
    target = discovery.normalize_chat(chat)
    chat_obj = await client.get_chat(target)
    result = PreviewResult(chat=_chat_info(chat_obj))

    async for message in discovery.iter_media_messages(
        client,
        target,
        types=types,
        limit=limit,
        min_id=min_id,
        max_id=max_id,
        since=since,
        until=until,
        caption_contains=caption_contains,
    ):
        result.items.append(_media_metadata(message))
        result.messages[message.id] = message

    return result
