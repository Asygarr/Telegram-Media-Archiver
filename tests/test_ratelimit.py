"""Unit test untuk penanganan FloodWait & retry transien (ratelimit)."""

from __future__ import annotations

import pytest
from pyrogram.errors import FloodWait

from tgdl.ratelimit import with_floodwait, with_retry


class _FW(FloodWait):
    """FloodWait ringan untuk pengujian tanpa jaringan."""

    def __init__(self, value: int) -> None:  # noqa: D401
        self.value = value


@pytest.mark.asyncio
async def test_floodwait_retries_then_succeeds() -> None:
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise _FW(0)
        return "ok"

    assert await with_floodwait(flaky) == "ok"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_floodwait_exhausted_raises() -> None:
    async def always_flood() -> str:
        raise _FW(0)

    with pytest.raises(FloodWait):
        await with_floodwait(always_flood, max_retries=2)


@pytest.mark.asyncio
async def test_with_retry_transient_then_success() -> None:
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("boom")
        return "done"

    assert await with_retry(flaky, retries=3, base=1.0) == "done"
    assert calls["n"] == 2
