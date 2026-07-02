"""Fixtures & helper bersama untuk pengujian tgdl."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

_MEDIA_ATTRS = (
    "photo",
    "video",
    "document",
    "audio",
    "voice",
    "video_note",
    "animation",
    "sticker",
)


def make_message(
    kind: str = "photo",
    msg_id: int = 1,
    fuid: str | None = "fuid1",
    chat_username: str | None = "grp",
    chat_id: int = -1001234567890,
    caption: str = "",
    file_name: str | None = None,
    file_size: int | None = 123,
) -> Any:
    """Buat objek pesan palsu yang menyerupai ``pyrogram.types.Message``."""
    media_obj = SimpleNamespace(
        file_unique_id=fuid, file_name=file_name, file_size=file_size
    )
    msg = SimpleNamespace(
        id=msg_id,
        media=SimpleNamespace(value=kind),
        chat=SimpleNamespace(id=chat_id, username=chat_username, title=None),
        from_user=SimpleNamespace(id=999),
        date=datetime(2026, 6, 30, 10, 12, 0),
        caption=caption,
    )
    for attr in _MEDIA_ATTRS:
        setattr(msg, attr, media_obj if attr == kind else None)
    return msg


@pytest.fixture
def message_factory():
    """Kembalikan factory ``make_message`` untuk dipakai di test."""
    return make_message
