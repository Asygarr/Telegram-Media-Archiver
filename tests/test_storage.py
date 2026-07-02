"""Unit test untuk penamaan file & dedup (storage)."""

from __future__ import annotations

from pathlib import Path

from tgdl.storage import Storage, build_output_path, sanitize, write_sidecar

from .conftest import make_message


def test_sanitize_removes_illegal_chars() -> None:
    assert sanitize('a/b:c*d?.txt') == "a_b_c_d_.txt"


def test_sanitize_truncates() -> None:
    assert len(sanitize("x" * 500, max_len=120)) == 120


def test_sanitize_empty_fallback() -> None:
    assert sanitize("   ") == "unnamed"


def test_build_output_path_deterministic() -> None:
    msg = make_message(kind="photo", msg_id=123, chat_username="grp")
    path = build_output_path(Path("downloads"), msg)
    assert path == Path("downloads/grp/photo/000123_photo.jpg")


def test_build_output_path_uses_id_when_no_username() -> None:
    msg = make_message(kind="video", msg_id=7, chat_username=None, chat_id=-42)
    path = build_output_path(Path("downloads"), msg)
    assert path == Path("downloads/id-42/video/000007_video.mp4")


def test_build_output_path_keeps_original_extension() -> None:
    msg = make_message(kind="document", msg_id=9, chat_username="grp", file_name="report.pdf")
    path = build_output_path(Path("downloads"), msg)
    assert path == Path("downloads/grp/document/000009_report.pdf")


def test_dedup_roundtrip(tmp_path: Path) -> None:
    db = Storage(tmp_path / "t.db")
    msg = make_message(msg_id=100, fuid="fuidX")
    assert not db.is_downloaded(msg.chat.id, msg.id, "fuidX")
    db.record(msg.chat.id, msg.id, "fuidX", tmp_path / "f.jpg", msg)
    assert db.is_downloaded(msg.chat.id, msg.id, "fuidX")
    db.close()


def test_write_sidecar(tmp_path: Path) -> None:
    msg = make_message(kind="video", msg_id=5, caption="hi")
    dest = tmp_path / "000005_video"
    sidecar = write_sidecar(dest, msg)
    assert sidecar.exists()
    assert sidecar.name == "000005_video.json"
    assert '"message_id": 5' in sidecar.read_text(encoding="utf-8")
