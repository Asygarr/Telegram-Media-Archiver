"""Web server lokal untuk gallery preview interaktif (aiohttp).

Menyajikan halaman gallery berisi thumbnail + metadata media, dengan checkbox
dan tombol Download yang memicu unduhan media terpilih melalui engine unduhan
yang sudah ada. Thumbnail diunduh secara *lazy* (saat ``GET /thumb/<id>``
pertama) lalu di-cache ke disk.

Keamanan: server hanya mengikat ``127.0.0.1`` dan setiap route memverifikasi
token acak yang disuntikkan ke URL saat browser dibuka.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
import webbrowser
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiohttp import web
from pyrogram import Client

from . import downloader
from .config import Settings
from .discovery import get_thumb_file_id
from .preview import PreviewResult
from .storage import Storage, thumb_cache_dir

log = logging.getLogger("tgdl.webserver")

_TEMPLATE = Path(__file__).parent / "templates" / "gallery.html"


class GalleryServer:
    """State & handler aiohttp untuk satu sesi preview gallery."""

    def __init__(
        self,
        client: Client,
        settings: Settings,
        storage: Storage,
        preview: PreviewResult,
        overwrite: bool = False,
        sidecar: bool = False,
    ) -> None:
        self.client = client
        self.settings = settings
        self.storage = storage
        self.preview = preview
        self.overwrite = overwrite
        self.sidecar = sidecar
        self.token = secrets.token_urlsafe(16)
        self.stop_event = asyncio.Event()
        self.thumb_sem = asyncio.Semaphore(max(1, settings.concurrency))
        self.progress: dict[int, dict[str, object]] = {}
        self.job_running = False
        self.job_task: asyncio.Task[None] | None = None

    # -- app wiring -------------------------------------------------------

    def build_app(self) -> web.Application:
        app = web.Application(middlewares=[self._token_mw])
        app.add_routes(
            [
                web.get("/", self._handle_index),
                web.get("/thumb/{mid}", self._handle_thumb),
                web.post("/download", self._handle_download),
                web.get("/progress", self._handle_progress),
                web.post("/shutdown", self._handle_shutdown),
            ]
        )
        return app

    @web.middleware
    async def _token_mw(
        self,
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        if not secrets.compare_digest(request.query.get("token", ""), self.token):
            return web.Response(status=403, text="forbidden")
        return await handler(request)

    # -- handlers ---------------------------------------------------------

    async def _handle_index(self, request: web.Request) -> web.Response:
        template = _TEMPLATE.read_text(encoding="utf-8")
        html = (
            template.replace("{{TOKEN}}", self.token)
            .replace("{{TITLE}}", _escape(self.preview.chat.title))
            .replace("{{ITEMS}}", json.dumps(self.preview.items))
        )
        return web.Response(text=html, content_type="text/html")

    async def _handle_thumb(self, request: web.Request) -> web.StreamResponse:
        try:
            mid = int(request.match_info["mid"])
        except ValueError:
            return web.Response(status=400, text="bad id")
        message = self.preview.messages.get(mid)
        if message is None:
            return web.Response(status=404, text="unknown message")

        dest = thumb_cache_dir(self.settings.download_dir, message) / f"{mid}.jpg"
        if not dest.exists():
            file_id = get_thumb_file_id(message)
            if file_id is None:
                return web.Response(status=404, text="no thumbnail")
            async with self.thumb_sem:
                if not dest.exists():
                    await downloader.download_thumbnail(self.client, file_id, dest)
        if dest.exists():
            return web.FileResponse(dest)
        return web.Response(status=404, text="thumbnail unavailable")

    async def _handle_download(self, request: web.Request) -> web.Response:
        if self.job_running:
            return web.json_response({"error": "job sedang berjalan"}, status=409)
        try:
            body = await request.json()
            ids = [int(x) for x in body.get("ids", [])]
        except (ValueError, json.JSONDecodeError):
            return web.json_response({"error": "payload tidak valid"}, status=400)
        ids = [mid for mid in ids if mid in self.preview.messages]
        if not ids:
            return web.json_response({"error": "tidak ada item valid"}, status=400)

        self.job_running = True
        self.progress = {
            mid: {"status": "queued", "current": 0, "total": 0, "error": None}
            for mid in ids
        }
        self.job_task = asyncio.create_task(self._run_job(ids))
        return web.json_response({"started": True, "count": len(ids)})

    async def _handle_progress(self, request: web.Request) -> web.Response:
        done = not self.job_running
        counts = {"downloaded": 0, "skipped": 0, "errors": 0, "pending": 0}
        for entry in self.progress.values():
            status = entry.get("status")
            if status == "ok":
                counts["downloaded"] += 1
            elif status == "skip":
                counts["skipped"] += 1
            elif status == "error":
                counts["errors"] += 1
            else:
                counts["pending"] += 1
        return web.json_response(
            {"done": done, "counts": counts, "items": self.progress}
        )

    async def _handle_shutdown(self, request: web.Request) -> web.Response:
        # Server berhenti via ``serve()`` yang lebih dulu menunggu job unduhan
        # yang masih berjalan agar tidak ada media terpilih yang terpotong.
        self.stop_event.set()
        return web.json_response({"ok": True, "job_running": self.job_running})

    # -- job runner -------------------------------------------------------

    async def _run_job(self, ids: list[int]) -> None:
        sem = asyncio.Semaphore(max(1, self.settings.concurrency))
        total = len(ids)
        done = 0
        log.info("Mulai mengunduh %d media terpilih…", total)

        async def worker(mid: int) -> None:
            nonlocal done
            message = self.preview.messages[mid]
            entry = self.progress[mid]

            def cb(current: int, total_bytes: int) -> None:
                entry["status"] = "downloading"
                entry["current"] = current
                entry["total"] = total_bytes

            async with sem:
                result = await downloader.download_one(
                    self.client,
                    message,
                    self.settings,
                    self.storage,
                    progress=cb,
                    overwrite=self.overwrite,
                    sidecar=self.sidecar,
                )
            entry["status"] = result.status
            entry["error"] = result.error
            done += 1
            log.info("[%d/%d] msg %s: %s", done, total, mid, result.status)

        try:
            await asyncio.gather(*(worker(mid) for mid in ids))
        finally:
            self.job_running = False
            ok = sum(1 for e in self.progress.values() if e.get("status") == "ok")
            skip = sum(1 for e in self.progress.values() if e.get("status") == "skip")
            err = sum(1 for e in self.progress.values() if e.get("status") == "error")
            log.info("Selesai: %d diunduh, %d dilewati (dedup), %d error", ok, skip, err)


def _escape(text: str) -> str:
    """Escape minimal untuk menyisipkan teks ke dalam HTML."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


async def serve(
    server: GalleryServer,
    host: str = "127.0.0.1",
    port: int = 8750,
    open_browser: bool = True,
) -> None:
    """Jalankan server gallery sampai ``stop_event`` diset (tombol Done/Ctrl+C)."""
    app = server.build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    url = f"http://{host}:{port}/?token={server.token}"
    log.info("Gallery preview aktif di %s", url)
    if open_browser:
        webbrowser.open(url)

    try:
        await server.stop_event.wait()
    finally:
        # Jangan memotong unduhan yang masih berjalan saat user menekan Selesai.
        if server.job_task is not None and not server.job_task.done():
            log.info("Menunggu unduhan yang masih berjalan selesai…")
            with contextlib.suppress(asyncio.CancelledError):
                await server.job_task
        await runner.cleanup()
