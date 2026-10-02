"""Tes untuk fitur gallery preview: thumbnail, metadata, dan web server."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from aiohttp.test_utils import TestClient, TestServer

from tgdl import discovery, webserver
from tgdl.downloader import DownloadResult
from tgdl.preview import collect_items
from tgdl.storage import thumb_cache_dir


def _msg_with_thumbs(msg_id: int, kind: str, thumb_id: str | None) -> Any:
    thumbs = [SimpleNamespace(file_id=thumb_id)] if thumb_id else None
    media = SimpleNamespace(
        file_unique_id=f"fuid{msg_id}",
        file_name=None,
        file_size=1000,
        width=640,
        height=480,
        duration=None,
        thumbs=thumbs,
    )
    msg = SimpleNamespace(
        id=msg_id,
        media=SimpleNamespace(value=kind),
        chat=SimpleNamespace(id=-100, username="grp", title="Grup", first_name=None),
        from_user=SimpleNamespace(id=1),
        date=datetime(2026, 6, 1, 12, 0, 0),
        caption="halo",
        photo=None,
    )
    for attr in ("photo", "video", "document", "audio", "voice",
                 "video_note", "animation", "sticker"):
        setattr(msg, attr, media if attr == kind else None)
    return msg


def test_get_thumb_file_id_prefers_thumbs() -> None:
    msg = _msg_with_thumbs(1, "video", thumb_id="small123")
    assert discovery.get_thumb_file_id(msg) == "small123"


def test_get_thumb_file_id_photo_fallback() -> None:
    photo = SimpleNamespace(file_unique_id="p", file_id="photoid", file_size=10)
    msg = SimpleNamespace(
        id=2, media=SimpleNamespace(value="photo"),
        photo=photo, video=None, document=None, audio=None, voice=None,
        video_note=None, animation=None, sticker=None,
    )
    assert discovery.get_thumb_file_id(msg) == "photoid"


def test_get_thumb_file_id_none_for_voice() -> None:
    media = SimpleNamespace(file_unique_id="v", file_size=10)  # no thumbs, no file_id
    msg = SimpleNamespace(
        id=3, media=SimpleNamespace(value="voice"), photo=None,
        video=None, document=None, audio=None, voice=media,
        video_note=None, animation=None, sticker=None,
    )
    assert discovery.get_thumb_file_id(msg) is None


def test_thumb_cache_dir_path(tmp_path: Path) -> None:
    msg = _msg_with_thumbs(1, "video", thumb_id="x")
    result = thumb_cache_dir(tmp_path, msg)
    assert result == tmp_path / "grp" / ".thumbs"


class _FakePreviewClient:
    def __init__(self, messages: list[Any], chat: Any) -> None:
        self._messages = messages
        self._chat = chat

    async def get_chat(self, target: Any) -> Any:
        return self._chat

    async def get_chat_history(self, chat: Any, **kwargs: Any) -> Any:
        for msg in self._messages:
            yield msg


async def test_collect_items_metadata_shape() -> None:
    chat = SimpleNamespace(id=-100, username="grp", title="Grup", first_name=None)
    messages = [_msg_with_thumbs(10, "video", "t10"), _msg_with_thumbs(11, "photo", "t11")]
    client = _FakePreviewClient(messages, chat)

    result = await collect_items(client, "@grp")

    assert result.chat.title == "Grup"
    assert len(result.items) == 2
    assert set(result.messages) == {10, 11}
    item = result.items[0]
    assert item["message_id"] == 10
    assert item["type"] == "video"
    assert item["has_thumb"] is True
    assert item["size"] == 1000


def _make_server(tmp_path: Path, messages: dict[int, Any]) -> webserver.GalleryServer:
    settings = SimpleNamespace(download_dir=tmp_path, concurrency=2)
    preview = SimpleNamespace(
        chat=SimpleNamespace(id=-100, title="Grup", username="grp"),
        items=[{"message_id": mid, "type": "video", "has_thumb": True} for mid in messages],
        messages=messages,
    )
    return webserver.GalleryServer(
        client=SimpleNamespace(), settings=settings, storage=SimpleNamespace(),
        preview=preview,  # type: ignore[arg-type]
    )


async def test_webserver_rejects_without_token(tmp_path: Path) -> None:
    server = _make_server(tmp_path, {})
    async with TestClient(TestServer(server.build_app())) as client:
        resp = await client.get("/progress")
        assert resp.status == 403


async def test_webserver_progress_shape(tmp_path: Path) -> None:
    server = _make_server(tmp_path, {})
    async with TestClient(TestServer(server.build_app())) as client:
        resp = await client.get("/progress", params={"token": server.token})
        assert resp.status == 200
        data = await resp.json()
        assert data["done"] is True
        assert set(data["counts"]) == {"downloaded", "skipped", "errors", "pending"}


async def test_webserver_download_enqueues(tmp_path: Path, monkeypatch: Any) -> None:
    msg = _msg_with_thumbs(5, "video", "t5")
    server = _make_server(tmp_path, {5: msg})

    async def fake_download_one(*args: Any, **kwargs: Any) -> DownloadResult:
        return DownloadResult(message_id=5, status="ok", path="x")

    monkeypatch.setattr(webserver.downloader, "download_one", fake_download_one)

    async with TestClient(TestServer(server.build_app())) as client:
        resp = await client.post(
            "/download", params={"token": server.token}, json={"ids": [5]}
        )
        assert resp.status == 200
        assert (await resp.json())["started"] is True

        for _ in range(50):
            prog = await client.get("/progress", params={"token": server.token})
            data = await prog.json()
            if data["done"]:
                break
        assert data["counts"]["downloaded"] == 1


async def test_webserver_download_rejects_invalid_ids(tmp_path: Path) -> None:
    server = _make_server(tmp_path, {5: _msg_with_thumbs(5, "video", "t5")})
    async with TestClient(TestServer(server.build_app())) as client:
        resp = await client.post(
            "/download", params={"token": server.token}, json={"ids": [999]}
        )
        assert resp.status == 400


async def test_webserver_shutdown_tracks_running_job(tmp_path: Path, monkeypatch: Any) -> None:
    msg = _msg_with_thumbs(7, "video", "t7")
    server = _make_server(tmp_path, {7: msg})
    started = asyncio.Event()

    async def slow_download_one(*args: Any, **kwargs: Any) -> DownloadResult:
        started.set()
        await asyncio.sleep(0.05)
        return DownloadResult(message_id=7, status="ok", path="x")

    monkeypatch.setattr(webserver.downloader, "download_one", slow_download_one)

    async with TestClient(TestServer(server.build_app())) as client:
        await client.post("/download", params={"token": server.token}, json={"ids": [7]})
        await started.wait()
        resp = await client.post("/shutdown", params={"token": server.token})
        data = await resp.json()
        assert data["job_running"] is True
        assert server.job_task is not None
        # Job tetap diselesaikan meski shutdown sudah diminta.
        await server.job_task
        assert server.progress[7]["status"] == "ok"

