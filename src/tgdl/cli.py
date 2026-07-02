"""Antarmuka baris perintah tgdl (Typer + Rich).

Perintah:
    tgdl download <chat> [OPTIONS]   Unduh media dari chat.
    tgdl login                       Export/refresh session string.
    tgdl info <chat>                 Info chat & hitung kandidat media (scan).
    tgdl list                        Daftar dialog yang dapat diakses.

Tidak pernah menampilkan kredensial atau session string di output.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from . import discovery, downloader
from .client import build_client
from .config import load_settings
from .logging_conf import configure_logging
from .storage import Storage

app = typer.Typer(help="Telegram Protected Media Downloader (MTProto)", no_args_is_help=True)
console = Console()


@app.command()
def download(
    chat: str = typer.Argument(..., help="Username, ID, atau link chat target"),
    types: str | None = typer.Option(None, "--types", help="mis. photo,video,document"),
    limit: int = typer.Option(0, "--limit", help="Batas jumlah pesan (0 = semua)"),
    min_id: int = typer.Option(0, "--min-id", help="Hanya pesan id > min-id"),
    max_id: int = typer.Option(0, "--max-id", help="Mulai dari id ini ke bawah"),
    out: str | None = typer.Option(None, "--out", help="Direktori output"),
    concurrency: int | None = typer.Option(None, "--concurrency", help="Unduhan paralel"),
    dry_run: bool = typer.Option(False, "--dry-run", help="List tanpa mengunduh"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Abaikan dedup"),
    sidecar: bool = typer.Option(False, "--sidecar", help="Tulis metadata .json per media"),
    log_level: str | None = typer.Option(None, "--log-level", help="DEBUG/INFO/WARNING/ERROR"),
) -> None:
    """Unduh media dari sebuah chat Telegram."""
    exit_code = asyncio.run(
        _download(
            chat, types, limit, min_id, max_id, out, concurrency, dry_run, overwrite,
            sidecar, log_level,
        )
    )
    raise typer.Exit(code=exit_code)


async def _download(
    chat: str,
    types: str | None,
    limit: int,
    min_id: int,
    max_id: int,
    out: str | None,
    concurrency: int | None,
    dry_run: bool,
    overwrite: bool,
    sidecar: bool,
    log_level: str | None,
) -> int:
    settings = load_settings()
    if out is not None:
        settings.download_dir = Path(out)
    if concurrency is not None:
        settings.concurrency = concurrency
    configure_logging(log_level or settings.log_level)

    try:
        type_set = discovery.parse_types(types)
    except ValueError as exc:
        console.print(f"[red]Error:[/] {exc}")
        return 2

    storage = Storage(settings.download_dir / "tgdl.db")

    async with build_client(settings) as client:
        messages = discovery.iter_media_messages(
            client, chat, type_set, limit=limit, min_id=min_id, max_id=max_id
        )

        if dry_run:
            count = 0
            async for msg in messages:
                media = msg.media.value if msg.media else "?"
                console.print(f"[dim]would download[/] msg {msg.id} ({media})")
                count += 1
            console.print(f"[bold]Total kandidat:[/] {count}")
            return 0

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:

            def progress_factory(msg):  # type: ignore[no-untyped-def]
                task_id = progress.add_task(f"msg {msg.id}", total=None)

                def cb(current: int, total: int) -> None:
                    progress.update(task_id, completed=current, total=total)

                return cb

            report = await downloader.run_batch(
                client,
                messages,
                settings,
                storage,
                progress_factory=progress_factory,
                overwrite=overwrite,
                sidecar=sidecar,
            )

    _print_report(report)
    return 0 if report.errors == 0 else 1


def _print_report(report: downloader.BatchReport) -> None:
    console.print()
    console.print(f"[green]\u2714 Downloaded:[/] {report.downloaded}")
    console.print(f"[yellow]\u21b7 Skipped (dedup):[/] {report.skipped}")
    console.print(f"[red]\u2717 Errors:[/] {report.errors}")
    for item in report.failed:
        console.print(f"  [red]- msg {item.message_id}:[/] {item.error}")


@app.command()
def login() -> None:
    """Login interaktif dan cetak session string (untuk disimpan di .env)."""
    from .auth import export_session_string

    settings = load_settings()
    configure_logging(settings.log_level)
    session = asyncio.run(export_session_string(settings))
    console.print("\n[bold]SESSION_STRING[/] (simpan ke .env, JANGAN commit):")
    console.print(session)


@app.command()
def info(chat: str = typer.Argument(..., help="Chat target")) -> None:
    """Tampilkan info chat & hitung kandidat media (scan, tanpa unduh)."""
    asyncio.run(_info(chat))


async def _info(chat: str) -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    async with build_client(settings) as client:
        target = await client.get_chat(chat)
        count = 0
        async for _ in discovery.iter_media_messages(client, chat):
            count += 1
        table = Table(title="Info Chat")
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("ID", str(target.id))
        table.add_row("Title/Username", str(target.title or target.username or "-"))
        table.add_row("Kandidat media", str(count))
        console.print(table)


@app.command(name="list")
def list_dialogs(limit: int = typer.Option(50, "--limit", help="Jumlah dialog")) -> None:
    """Daftar dialog (chat) yang dapat diakses akun."""
    asyncio.run(_list(limit))


async def _list(limit: int) -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    async with build_client(settings) as client:
        table = Table(title="Dialogs")
        table.add_column("ID")
        table.add_column("Type")
        table.add_column("Title/Username")
        async for dialog in client.get_dialogs(limit=limit):
            chat = dialog.chat
            table.add_row(
                str(chat.id),
                str(chat.type.value if chat.type else "-"),
                str(chat.title or chat.username or chat.first_name or "-"),
            )
        console.print(table)


if __name__ == "__main__":
    app()
