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


def _code128_size(value: str, available_width: int) -> tuple[int, int]:
    # Start, data, checksum and stop symbols. Code Set B uses one symbol per
    # character; every symbol is 11 modules except the 13-module stop symbol.
    modules = (len(value) + 2) * 11 + 13
    module_width = min(2, available_width // modules)
    if module_width < 2:
        raise ValueError("Barcode is too long to print reliably on a 50 mm label")
    return module_width, modules * module_width


def build_label(item: CatalogItem, quantity: int, settings: Settings) -> bytes:
    if not item.barcode:
        raise ValueError(f"{item.item_code} does not have a barcode")
    barcode = safe_barcode(item.barcode)
    item_code = safe_sbpl_text(item.item_code, 36)
    description = safe_sbpl_text(item.description, 200)
    description_lines = textwrap.wrap(
        description,
        width=43,
        break_long_words=True,
        break_on_hyphens=True,
    )[:3] or [item_code]

    width = settings.label_width_dots
    height = settings.label_height_dots
    if width != 600 or height != 360:
        raise ValueError("The current label layout supports 50 x 30 mm at 12 dots/mm")

    barcode_module, barcode_width = _code128_size(barcode, width - 64)
    barcode_x = max(32, (width - barcode_width) // 2)
    item_text_width = len(item_code) * 16
    item_x = max(20, (width - item_text_width) // 2)

    payload = bytearray()
    payload += _command("A")
    payload += _command(f"A1{height:04d}{width:04d}")
    payload += _command("H0020") + _command("V0010") + _command("L0101")
    payload += _command("M") + description_lines[0].encode("ascii")
    if len(description_lines) > 1:
        payload += _command("H0020") + _command("V0032") + _command("M")
        payload += description_lines[1].encode("ascii")
    if len(description_lines) > 2:
        payload += _command("H0020") + _command("V0054") + _command("M")
        payload += description_lines[2].encode("ascii")
    payload += _command(f"H{barcode_x:04d}") + _command("V0084")
    payload += _command(f"BG{barcode_module:02d}190") + b">F" + barcode.encode("ascii")
    payload += _command(f"H{item_x:04d}") + _command("V0306") + _command("L0202")
    payload += _command("S") + item_code.encode("ascii")
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
