"""Integration test engine unduhan dengan client mock (tanpa jaringan)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tgdl.downloader import DownloadResult, download_one, save_failed_report, summarize
from tgdl.storage import Storage

from .conftest import make_message


def _settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(download_dir=tmp_path / "downloads", concurrency=2)


def _fake_client(tmp_path: Path) -> AsyncMock:
    client = AsyncMock()

    async def fake_download(message, file_name, progress=None):  # type: ignore[no-untyped-def]
        p = Path(file_name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"data")
        return str(p)

    client.download_media = AsyncMock(side_effect=fake_download)
    return client


@pytest.mark.asyncio
async def test_download_one_ok(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    storage = Storage(settings.download_dir / "tgdl.db")
    client = _fake_client(tmp_path)
    msg = make_message(kind="photo", msg_id=1, fuid="f1")

    result = await download_one(client, msg, settings, storage)

    assert result.status == "ok"
    assert Path(result.path).exists()
    client.download_media.assert_awaited_once()
    storage.close()


@pytest.mark.asyncio
async def test_download_one_dedup_skip(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    storage = Storage(settings.download_dir / "tgdl.db")
    client = _fake_client(tmp_path)
    msg = make_message(kind="photo", msg_id=2, fuid="f2")

    first = await download_one(client, msg, settings, storage)
    second = await download_one(client, msg, settings, storage)

    assert first.status == "ok"
    assert second.status == "skip"
    client.download_media.assert_awaited_once()  # tidak diunduh lagi
    storage.close()


@pytest.mark.asyncio
async def test_download_one_failsoft(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    storage = Storage(settings.download_dir / "tgdl.db")
    client = AsyncMock()
    client.download_media = AsyncMock(side_effect=RuntimeError("kaboom"))
    msg = make_message(kind="video", msg_id=3, fuid="f3")

    result = await download_one(client, msg, settings, storage)

    assert result.status == "error"
    assert "kaboom" in (result.error or "")
    storage.close()


def test_summarize_counts() -> None:
    results = [
        DownloadResult(1, "ok"),
        DownloadResult(2, "skip"),
        DownloadResult(3, "error", error="x"),
    ]
    report = summarize(results)
    assert (report.downloaded, report.skipped, report.errors) == (1, 1, 1)
    assert len(report.failed) == 1


def test_save_failed_report(tmp_path: Path) -> None:
    failed = [DownloadResult(9, "error", error="boom")]
    path = save_failed_report(tmp_path, failed)
    assert path is not None and path.exists()
    assert '"message_id": 9' in path.read_text(encoding="utf-8")


def test_save_failed_report_empty(tmp_path: Path) -> None:
    assert save_failed_report(tmp_path, []) is None
