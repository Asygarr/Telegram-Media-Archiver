"""Unit test untuk filter tipe media (discovery)."""

from __future__ import annotations

import pytest
from pyrogram.enums import MessageMediaType

from tgdl.discovery import get_file_unique_id, parse_types

from .conftest import make_message


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
