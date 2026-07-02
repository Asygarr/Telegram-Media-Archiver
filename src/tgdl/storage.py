"""Penyimpanan file & metadata untuk tgdl.

Versi dasar: penamaan file aman, path output deterministik, dan SQLite untuk
dedup/resume. Disempurnakan pada Fase 08 (sidecar JSON, penulisan atomik).
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import sqlite3
from pathlib import Path

from pyrogram.types import Message

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

_SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    chat_id         INTEGER NOT NULL,
    message_id      INTEGER NOT NULL,
    file_unique_id  TEXT,
    media_type      TEXT,
    file_path       TEXT,
    file_size       INTEGER,
    caption         TEXT,
    sender_id       INTEGER,
    message_date    TEXT,
    downloaded_at   TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (chat_id, message_id, file_unique_id)
);
CREATE INDEX IF NOT EXISTS idx_fuid ON downloads(file_unique_id);
"""


def sanitize(name: str, max_len: int = 120) -> str:
    """Sanitasi nama menjadi aman untuk filesystem lintas-OS."""
    cleaned = _ILLEGAL.sub("_", name).strip().strip(".")
    cleaned = cleaned[:max_len]
    return cleaned or "unnamed"


def media_kind(message: Message) -> str:
    """Nama tipe media pesan (untuk subfolder)."""
    return message.media.value if message.media else "other"


# Ekstensi cadangan bila media tak punya file_name / mime_type.
_EXT_BY_KIND = {
    "photo": ".jpg",
    "video": ".mp4",
    "video_note": ".mp4",
    "animation": ".mp4",
    "voice": ".ogg",
    "audio": ".mp3",
    "sticker": ".webp",
}


def _real_filename(message: Message) -> str | None:
    """Nama file asli dari media (document/audio/video/...) bila tersedia."""
    for attr in ("document", "audio", "video", "animation", "voice"):
        media = getattr(message, attr, None)
        fname = getattr(media, "file_name", None) if media is not None else None
        if fname:
            return str(fname)
    return None


def _media_with_mime(message: Message) -> object | None:
    return (
        message.document
        or message.video
        or message.audio
        or message.animation
        or message.voice
        or message.video_note
    )


def guess_extension(message: Message) -> str:
    """Tebak ekstensi file: dari nama asli -> mime_type -> cadangan per tipe."""
    real = _real_filename(message)
    if real:
        suffix = Path(real).suffix
        if suffix:
            return suffix
    media = _media_with_mime(message)
    mime = getattr(media, "mime_type", None) if media is not None else None
    if mime:
        ext = mimetypes.guess_extension(mime)
        if ext:
            return ".jpg" if ext in (".jpe", ".jpeg") else ext
    return _EXT_BY_KIND.get(media_kind(message), "")


def _file_size(message: Message) -> int | None:
    media = _media_with_mime(message)
    return getattr(media, "file_size", None) if media is not None else None


def build_output_path(base: Path, message: Message) -> Path:
    """Bangun path output deterministik: ``base/<chat_slug>/<tipe>/<id6>_<nama><ext>``."""
    kind = media_kind(message)
    chat_slug = sanitize(message.chat.username or f"id{message.chat.id}")
    real = _real_filename(message)
    stem = sanitize(real) if real else kind
    ext = guess_extension(message)
    # Hindari ekstensi ganda bila nama asli sudah mengandungnya.
    if ext and stem.lower().endswith(ext.lower()):
        stem = stem[: -len(ext)]
    fname = f"{message.id:06d}_{stem}{ext}"
    return base / chat_slug / kind / fname



def part_path(dest: Path) -> Path:
    """Path sementara ``.part`` untuk penulisan atomik."""
    return dest.with_name(dest.name + ".part")


def finalize_atomic(tmp: Path, dest: Path) -> Path:
    """Pindahkan file sementara ``tmp`` menjadi ``dest``.

    Utamakan ``os.replace`` (atomik, satu drive). Bila gagal karena beda drive
    (Windows ``[WinError 17]``) atau kasus lintas-filesystem, fallback ke
    ``shutil.move`` (salin lalu hapus).
    """
    try:
        os.replace(tmp, dest)
    except OSError:
        shutil.move(str(tmp), str(dest))
    return dest


def write_sidecar(dest: Path, message: Message) -> Path:
    """Tulis metadata media ke sidecar ``<dest>.json`` (FR-14)."""
    meta = {
        "message_id": message.id,
        "chat": message.chat.username or f"id{message.chat.id}",
        "chat_id": message.chat.id,
        "date": str(message.date) if message.date else None,
        "sender_id": getattr(message.from_user, "id", None),
        "caption": message.caption or "",
        "media_type": media_kind(message),
        "file_size": _file_size(message),
    }
    sidecar = dest.with_name(dest.name + ".json")
    sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return sidecar


class Storage:
    """Lapisan metadata SQLite untuk dedup & resume."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def is_downloaded(
        self, chat_id: int, message_id: int, file_unique_id: str | None
    ) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM downloads "
            "WHERE chat_id = ? AND message_id = ? AND file_unique_id IS ?",
            (chat_id, message_id, file_unique_id),
        )
        return cur.fetchone() is not None

    def record(
        self,
        chat_id: int,
        message_id: int,
        file_unique_id: str | None,
        path: Path,
        message: Message,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO downloads "
            "(chat_id, message_id, file_unique_id, media_type, file_path, "
            " file_size, caption, sender_id, message_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                chat_id,
                message_id,
                file_unique_id,
                media_kind(message),
                str(path),
                _file_size(message),
                message.caption or "",
                getattr(message.from_user, "id", None),
                str(message.date) if message.date else None,
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
