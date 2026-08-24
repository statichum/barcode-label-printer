from __future__ import annotations

import json
import re
import socket
import textwrap
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from .config import Settings
from .database import CatalogItem
from .printer import PrinterDiscovery


ESC = b"\x1b"


def safe_sbpl_text(value: str, max_length: int = 100) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = " ".join(value.replace("\x1b", "").split())
    return value[:max_length]


def safe_barcode(value: str) -> str:
    cleaned = safe_sbpl_text(value, 100)
    if (
        not cleaned
        or len(cleaned) > 24
        or not re.fullmatch(r"[0-9A-Za-z._/+%$ -]+", cleaned)
    ):
        raise ValueError("Barcode contains unsupported characters")
    return cleaned


def _command(code: str) -> bytes:
    return ESC + code.encode("ascii")


def build_label(item: CatalogItem, quantity: int, settings: Settings) -> bytes:
    if not item.barcode:
        raise ValueError(f"{item.item_code} does not have a barcode")
    barcode = safe_barcode(item.barcode)
    item_code = safe_sbpl_text(item.item_code, 36)
    description = safe_sbpl_text(item.description, 100)
    description_lines = textwrap.wrap(
        description,
        width=33,
        break_long_words=True,
        break_on_hyphens=True,
    )[:2] or [item_code]

    width = settings.label_width_dots
    height = settings.label_height_dots
    if width != 600 or height != 360:
        raise ValueError("The current label layout supports 50 x 30 mm at 12 dots/mm")

    payload = bytearray()
    payload += _command("A")
    payload += _command(f"A1{height:04d}{width:04d}")
    payload += _command("H0018") + _command("V0018") + _command("L0101")
    payload += _command("XS") + description_lines[0].encode("ascii")
    if len(description_lines) > 1:
        payload += _command("H0018") + _command("V0043") + _command("XS")
        payload += description_lines[1].encode("ascii")
    payload += _command("H0018") + _command("V0080") + _command("L0101")
    payload += _command("XM") + item_code.encode("ascii")
    payload += _command("H0024") + _command("V0130")
    payload += _command("BG02095") + b">F" + barcode.encode("ascii")
    payload += _command("H0024") + _command("V0250") + _command("L0101")
    payload += _command("XS") + barcode.encode("ascii")
    payload += _command(f"Q{quantity}")
    payload += _command("Z")
    return bytes(payload)


@dataclass
class PrintService:
    settings: Settings
    discovery: PrinterDiscovery

    def print_items(
        self,
        items: list[tuple[CatalogItem, int]],
        source: str,
        reference: str | None,
    ) -> dict:
        payload = b"".join(
            build_label(item, quantity, self.settings) for item, quantity in items
        )
        label_count = sum(quantity for _, quantity in items)
        job_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        self.settings.spool_dir.mkdir(parents=True, exist_ok=True)
        sbpl_path = self.settings.spool_dir / f"{job_id}.sbpl"
        metadata_path = self.settings.spool_dir / f"{job_id}.json"
        sbpl_path.write_bytes(payload)

        status = "dry-run"
        printer_ip = None
        if self.settings.print_enabled:
            printer_ip = self.discovery.send(payload)
            status = "submitted"

        metadata = {
            "job_id": job_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "source": source,
            "reference": reference,
            "label_count": label_count,
            "items": [
                {"item_code": item.item_code, "barcode": item.barcode, "quantity": quantity}
                for item, quantity in items
            ],
            "printer": {
                "name": self.settings.printer_name,
                "model": self.settings.printer_model,
                "language": self.settings.printer_language,
                "ip": printer_ip,
                "port": self.settings.printer_port,
            },
            "host": socket.gethostname(),
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata
