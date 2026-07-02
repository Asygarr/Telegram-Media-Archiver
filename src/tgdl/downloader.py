"""Engine unduhan media asinkron untuk tgdl.

Mengunduh media (termasuk dari chat protected) secara async, dedup-aware, dan
fail-soft, dengan concurrency terkontrol dan penanganan FloodWait.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path

from pyrogram import Client
from pyrogram.types import Message

from .config import Settings
from .discovery import get_file_unique_id
from .ratelimit import safe_download
from .storage import Storage, build_output_path, finalize_atomic, part_path, write_sidecar

log = logging.getLogger("tgdl.downloader")

ProgressFactory = Callable[[Message], Callable[[int, int], None] | None]


@dataclass
class DownloadResult:
    """Hasil unduhan satu pesan."""

    message_id: int
    status: str  # "ok" | "skip" | "error"
    path: str | None = None
    error: str | None = None


@dataclass
class BatchReport:
    """Ringkasan hasil batch unduhan."""

    downloaded: int = 0
    skipped: int = 0
    errors: int = 0
    failed: list[DownloadResult] = field(default_factory=list)


async def download_one(
    client: Client,
    message: Message,
    settings: Settings,
    storage: Storage,
    progress: Callable[[int, int], None] | None = None,
    overwrite: bool = False,
    sidecar: bool = False,
) -> DownloadResult:
    """Unduh media satu pesan dengan dedup, FloodWait handling, dan fail-soft.

    Unduhan ditulis ke berkas sementara ``.part`` lalu dipindahkan secara atomik ke
    tujuan akhir, mencegah file korup bila proses terputus.
    """
    fuid = get_file_unique_id(message)
    if not overwrite and storage.is_downloaded(message.chat.id, message.id, fuid):
        return DownloadResult(message.id, "skip")

    dest = build_output_path(settings.download_dir, message)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = part_path(dest)

    try:
        path = await safe_download(client, message, str(tmp), progress)
        if path is None:
            return DownloadResult(message.id, "error", error="download_media returned None")
        finalize_atomic(Path(path), dest)
        if sidecar:
            write_sidecar(dest, message)
        storage.record(message.chat.id, message.id, fuid, dest, message)
        return DownloadResult(message.id, "ok", path=str(dest))
    except Exception as exc:  # fail-soft: satu item gagal tak menghentikan batch
        log.error("Gagal mengunduh pesan %s: %s", message.id, exc)
        return DownloadResult(message.id, "error", error=str(exc))


def summarize(results: list[DownloadResult]) -> BatchReport:
    """Ringkas daftar hasil menjadi laporan batch."""
    report = BatchReport()
    for r in results:
        if r.status == "ok":
            report.downloaded += 1
        elif r.status == "skip":
            report.skipped += 1
        else:
            report.errors += 1
            report.failed.append(r)
    return report


def save_failed_report(download_dir: Path, failed: list[DownloadResult]) -> Path | None:
    """Tulis daftar item gagal ke ``<download_dir>/_failed.json`` untuk retry terpisah."""
    if not failed:
        return None
    download_dir.mkdir(parents=True, exist_ok=True)
    path = download_dir / "_failed.json"
    data = [{"message_id": r.message_id, "error": r.error} for r in failed]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def run_batch(
    client: Client,
    messages: AsyncIterator[Message],
    settings: Settings,
    storage: Storage,
    progress_factory: ProgressFactory | None = None,
    overwrite: bool = False,
    sidecar: bool = False,
) -> BatchReport:
    """Jalankan unduhan batch dengan concurrency terkontrol (Semaphore)."""
    sem = asyncio.Semaphore(settings.concurrency)

    async def worker(msg: Message) -> DownloadResult:
        async with sem:
            progress = progress_factory(msg) if progress_factory else None
            return await download_one(
                client,
                msg,
                settings,
                storage,
                progress=progress,
                overwrite=overwrite,
                sidecar=sidecar,
            )

    tasks = [asyncio.create_task(worker(m)) async for m in messages]
    results = [await coro for coro in asyncio.as_completed(tasks)]
    report = summarize(results)
    save_failed_report(settings.download_dir, report.failed)
    return report
