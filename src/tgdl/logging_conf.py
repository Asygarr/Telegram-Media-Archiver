"""Konfigurasi logging untuk tgdl.

Versi dasar. Disempurnakan pada Fase 09 (format terstruktur lanjutan).
Aturan penting: JANGAN pernah mencatat kredensial atau session string.
"""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """Siapkan logging root dengan format ringkas dan redam log verbose pyrogram."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
