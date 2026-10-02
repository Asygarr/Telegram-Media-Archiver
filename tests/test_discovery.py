"""Unit test untuk filter tipe media (discovery)."""

from __future__ import annotations

from datetime import datetime

import pytest
from pyrogram.enums import MessageMediaType

from tgdl.discovery import get_file_unique_id, iter_media_messages, parse_date, parse_types

from .conftest import FakeHistoryClient, make_message


def test_parse_types_none() -> None:
    assert parse_types(None) is None
    assert parse_types("") is None


def test_parse_types_valid() -> None:
    result = parse_types("photo,video")
    assert result == {MessageMediaType.PHOTO, MessageMediaType.VIDEO}


def test_parse_types_trims_and_lowercases() -> None:
    assert parse_types(" Photo , VIDEO ") == {
        MessageMediaType.PHOTO,
        MessageMediaType.VIDEO,
    }


def test_parse_types_invalid_raises() -> None:
    with pytest.raises(ValueError):
        parse_types("photo,unknown")


def test_get_file_unique_id() -> None:
    msg = make_message(kind="document", fuid="abc123")
    assert get_file_unique_id(msg) == "abc123"


def test_parse_date_date_only_start_of_day() -> None:
    dt = parse_date("2026-06-30")
    assert dt.year == 2026 and dt.month == 6 and dt.day == 30
    assert dt.hour == 0 and dt.minute == 0 and dt.second == 0
    assert dt.tzinfo is not None


def test_parse_date_date_only_end_of_day() -> None:
    dt = parse_date("2026-06-30", end_of_day=True)
    assert (dt.hour, dt.minute, dt.second) == (23, 59, 59)


def test_parse_date_full_datetime_preserved() -> None:
    dt = parse_date("2026-06-30 08:15:00")
    assert (dt.hour, dt.minute, dt.second) == (8, 15, 0)


def test_parse_date_invalid_raises() -> None:
    with pytest.raises(ValueError):
        parse_date("not-a-date")


@pytest.mark.asyncio
async def test_iter_media_messages_since_breaks_on_older() -> None:
    # Riwayat terbaru->terlama: msg 3 (30/06) lolos `since`, msg 2 & 1 (lebih lama) tidak.
    msg3 = make_message(msg_id=3, caption="c3")
    msg3.date = datetime(2026, 6, 30, 10, 0, 0)
    msg2 = make_message(msg_id=2, caption="c2")
    msg2.date = datetime(2026, 6, 29, 10, 0, 0)
    msg1 = make_message(msg_id=1, caption="c1")
    msg1.date = datetime(2026, 6, 28, 10, 0, 0)
    client = FakeHistoryClient([msg3, msg2, msg1])

    since = datetime(2026, 6, 29, 12, 0, 0)  # setelah msg2, sebelum msg3
    results = [m async for m in iter_media_messages(client, "chat", since=since)]

    assert [m.id for m in results] == [3]


@pytest.mark.asyncio
async def test_iter_media_messages_until_skips_newer() -> None:
    msg3 = make_message(msg_id=3)
    msg3.date = datetime(2026, 6, 30, 10, 0, 0)
    msg2 = make_message(msg_id=2)
    msg2.date = datetime(2026, 6, 29, 10, 0, 0)
    msg1 = make_message(msg_id=1)
    msg1.date = datetime(2026, 6, 28, 10, 0, 0)
    client = FakeHistoryClient([msg3, msg2, msg1])

    until = datetime(2026, 6, 29, 12, 0, 0)
    results = [m async for m in iter_media_messages(client, "chat", until=until)]

    assert [m.id for m in results] == [2, 1]


@pytest.mark.asyncio
async def test_iter_media_messages_caption_contains_case_insensitive() -> None:
    msg_match = make_message(msg_id=1, caption="Hello World")
    msg_no_match = make_message(msg_id=2, caption="Something else")
    client = FakeHistoryClient([msg_match, msg_no_match])

    results = [
        m async for m in iter_media_messages(client, "chat", caption_contains="world")
    ]

    assert [m.id for m in results] == [1]
