from __future__ import annotations

import json
import re
import socket
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from .config import Settings
from .database import CatalogItem
from .printer import PrinterDiscovery


ESC = b"\x1b"
DESCRIPTION_MARGIN_DOTS = 40
DESCRIPTION_FONT_WIDTH_DOTS = 18
DESCRIPTION_FONT_HEIGHT_DOTS = 32
DESCRIPTION_LINE_ADVANCE_DOTS = 35
ITEM_CODE_MARGIN_DOTS = 32
ITEM_CODE_PREFERRED_CELL_WIDTH_DOTS = 30
ITEM_CODE_PREFERRED_WIDTH_DOTS = 31
ITEM_CODE_PREFERRED_HEIGHT_DOTS = 65
ITEM_CODE_BOTTOM_MARGIN_DOTS = 19
ITEM_CODE_OVERPRINT_DOTS = 6
BARCODE_HEIGHT_DOTS = 126

LARGE_LABEL_MARGIN_DOTS = 48
LARGE_DESCRIPTION_FONT_WIDTH_DOTS = 46
LARGE_DESCRIPTION_FONT_HEIGHT_DOTS = 64
LARGE_DESCRIPTION_LINE_ADVANCE_DOTS = 74
LARGE_BARCODE_HEIGHT_DOTS = 300
LARGE_ITEM_CODE_MAX_WIDTH_DOTS = 76
LARGE_ITEM_CODE_MAX_HEIGHT_DOTS = 120


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


def safe_zpl_text(value: str, max_length: int = 200) -> str:
    """Keep user text from being interpreted as a ZPL command."""
    cleaned = safe_sbpl_text(value, max_length)
    return cleaned.replace("^", "").replace("~", "").replace("\\", "")


def _command(code: str) -> bytes:
    return ESC + code.encode("ascii")


def _description_line(text: str, y: int) -> bytes:
    font_command = (
        f"RDB01,{DESCRIPTION_FONT_WIDTH_DOTS:03d},"
        f"{DESCRIPTION_FONT_HEIGHT_DOTS:03d},"
    )
    encoded = text.encode("ascii")
    return (
        _command(f"H{DESCRIPTION_MARGIN_DOTS:04d}")
        + _command(f"V{y:04d}")
        + _command(font_command)
        + encoded
        + _command(f"H{DESCRIPTION_MARGIN_DOTS + 1:04d}")
        + _command(f"V{y:04d}")
        + _command(font_command)
        + encoded
    )


def _estimated_character_width(character: str, font_width: int) -> int:
    if character in " .,:;!|iIl1'`":
        factor = 0.35
    elif character in "MW@%&QO0":
        factor = 1.0
    elif character.isupper():
        factor = 0.72
    elif character.isdigit():
        factor = 0.62
    else:
        factor = 0.56
    return max(1, round(font_width * factor))


def _estimated_text_width(value: str, font_width: int) -> int:
    return sum(_estimated_character_width(character, font_width) for character in value)


def _wrap_proportional_text(
    value: str, available_width: int, font_width: int, max_lines: int
) -> list[str]:
    lines: list[str] = []
    remaining = value.strip()
    while remaining and len(lines) < max_lines:
        if _estimated_text_width(remaining, font_width) <= available_width:
            lines.append(remaining)
            break

        width = 0
        last_space = -1
        cut = 0
        for index, character in enumerate(remaining):
            character_width = _estimated_character_width(character, font_width)
            if width + character_width > available_width:
                break
            width += character_width
            cut = index + 1
            if character == " ":
                last_space = index

        if last_space > 0:
            lines.append(remaining[:last_space].rstrip())
            remaining = remaining[last_space + 1 :].lstrip()
        else:
            cut = max(1, cut)
            lines.append(remaining[:cut].rstrip())
            remaining = remaining[cut:].lstrip()
    return lines


def _fixed_pitch_smooth_text(
    value: str,
    x: int,
    y: int,
    cell_width: int,
    font_width: int,
    font_height: int,
) -> bytes:
    font_command = f"RDB01,{font_width:03d},{font_height:03d},"
    payload = bytearray()
    for index, character in enumerate(value):
        glyph_width = min(
            font_width, _estimated_character_width(character, font_width)
        )
        glyph_x = x + (index * cell_width) + ((cell_width - glyph_width) // 2)
        encoded = character.encode("ascii")
        for offset in range(ITEM_CODE_OVERPRINT_DOTS):
            payload += _command(f"H{glyph_x + offset:04d}") + _command(f"V{y:04d}")
            payload += _command(font_command) + encoded
    return bytes(payload)


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

    width = settings.label_width_dots
    height = settings.label_height_dots
    if width != 600 or height != 360:
        raise ValueError("The current label layout supports 50 x 30 mm at 12 dots/mm")
    if settings.printer_print_speed not in {2, 3, 4}:
        raise ValueError("PRINTER_PRINT_SPEED must be 2, 3, or 4")
    if settings.printer_darkness not in {f"{level}A" for level in range(1, 6)}:
        raise ValueError("PRINTER_DARKNESS must be between 1A and 5A")

    description_width = width - (DESCRIPTION_MARGIN_DOTS * 2) - 1
    description_lines = _wrap_proportional_text(
        description,
        available_width=description_width,
        font_width=DESCRIPTION_FONT_WIDTH_DOTS,
        max_lines=3,
    ) or [item_code]

    barcode_module, barcode_width = _code128_size(barcode, width - 64)
    barcode_x = max(32, (width - barcode_width) // 2)
    item_available_width = width - (ITEM_CODE_MARGIN_DOTS * 2)
    item_cell_width = min(
        ITEM_CODE_PREFERRED_CELL_WIDTH_DOTS,
        (item_available_width - ITEM_CODE_OVERPRINT_DOTS) // len(item_code),
    )
    item_font_width = min(
        ITEM_CODE_PREFERRED_WIDTH_DOTS,
        (item_available_width - ITEM_CODE_OVERPRINT_DOTS) // len(item_code),
    )
    item_font_height = round(
        ITEM_CODE_PREFERRED_HEIGHT_DOTS
        * (item_font_width / ITEM_CODE_PREFERRED_WIDTH_DOTS)
    )
    item_text_width = (len(item_code) * item_cell_width) + ITEM_CODE_OVERPRINT_DOTS - 1
    item_x = max(ITEM_CODE_MARGIN_DOTS, (width - item_text_width) // 2)
    item_y = height - ITEM_CODE_BOTTOM_MARGIN_DOTS - item_font_height

    description_y = 10
    description_bottom = (
        description_y
        + ((len(description_lines) - 1) * DESCRIPTION_LINE_ADVANCE_DOTS)
        + DESCRIPTION_FONT_HEIGHT_DOTS
    )
    available_vertical_gap = item_y - description_bottom - BARCODE_HEIGHT_DOTS
    barcode_top_gap = max(8, round(available_vertical_gap * 0.4))
    barcode_y = description_bottom + barcode_top_gap

    payload = bytearray()
    payload += _command("A")
    payload += _command(f"CS{settings.printer_print_speed}")
    payload += _command(f"#E{settings.printer_darkness}")
    payload += _command(f"A1{height:04d}{width:04d}")
    payload += _description_line(description_lines[0], description_y)
    if len(description_lines) > 1:
        payload += _description_line(
            description_lines[1], description_y + DESCRIPTION_LINE_ADVANCE_DOTS
        )
    if len(description_lines) > 2:
        payload += _description_line(
            description_lines[2], description_y + (DESCRIPTION_LINE_ADVANCE_DOTS * 2)
        )
    payload += _command(f"H{barcode_x:04d}") + _command(f"V{barcode_y:04d}")
    payload += _command(f"BG{barcode_module:02d}{BARCODE_HEIGHT_DOTS:03d}")
    payload += b">F" + barcode.encode("ascii")
    payload += _fixed_pitch_smooth_text(
        item_code,
        x=item_x,
        y=item_y,
        cell_width=item_cell_width,
        font_width=item_font_width,
        font_height=item_font_height,
    )
    payload += _command(f"Q{quantity}")
    payload += _command("Z")
    return bytes(payload)


def build_large_label(item: CatalogItem, quantity: int, settings: Settings) -> bytes:
    """Build a landscape composition on 100 x 175 mm Zebra media."""
    if not item.barcode:
        raise ValueError(f"{item.item_code} does not have a barcode")
    barcode = safe_barcode(item.barcode)
    item_code = safe_zpl_text(item.item_code, 36)
    description = safe_zpl_text(item.description, 240)
    width = settings.label_width_dots
    height = settings.label_height_dots
    if width != 800 or height != 1400:
        raise ValueError("The large label layout supports 100 x 175 mm at 8 dots/mm")

    # The physical web is 800 dots wide and advances 1,400 dots per label. All
    # fields are rotated clockwise so the readable canvas is 1,400 x 800.
    landscape_width = height
    landscape_height = width
    available_width = landscape_width - (LARGE_LABEL_MARGIN_DOTS * 2)
    description_lines = _wrap_proportional_text(
        description,
        available_width=available_width,
        font_width=LARGE_DESCRIPTION_FONT_WIDTH_DOTS,
        max_lines=3,
    ) or [item_code]
    description_y = LARGE_LABEL_MARGIN_DOTS
    description_bottom = (
        description_y
        + ((len(description_lines) - 1) * LARGE_DESCRIPTION_LINE_ADVANCE_DOTS)
        + LARGE_DESCRIPTION_FONT_HEIGHT_DOTS
    )

    barcode_module, barcode_width = _code128_size(barcode, available_width)
    barcode_x = max(290, description_bottom + 58)
    barcode_y = max(LARGE_LABEL_MARGIN_DOTS, (landscape_width - barcode_width) // 2)

    item_font_width = min(
        LARGE_ITEM_CODE_MAX_WIDTH_DOTS,
        max(20, available_width // max(1, len(item_code))),
    )
    item_font_height = min(
        LARGE_ITEM_CODE_MAX_HEIGHT_DOTS,
        round(LARGE_ITEM_CODE_MAX_HEIGHT_DOTS * item_font_width / LARGE_ITEM_CODE_MAX_WIDTH_DOTS),
    )
    item_text_width = _estimated_text_width(item_code, item_font_width)
    item_x = min(
        landscape_height - LARGE_LABEL_MARGIN_DOTS - item_font_height,
        barcode_x + LARGE_BARCODE_HEIGHT_DOTS + 85,
    )
    item_y = max(LARGE_LABEL_MARGIN_DOTS, (landscape_width - item_text_width) // 2)

    payload = [
        "^XA",
        f"^PW{width}",
        f"^LL{height}",
        "^LH0,0",
        f"^PR{settings.printer_print_speed}",
        f"~SD{settings.large_printer_darkness}",
        "^FWR",
    ]
    for index, line in enumerate(description_lines):
        x = description_y + (index * LARGE_DESCRIPTION_LINE_ADVANCE_DOTS)
        payload.append(
            f"^FO{x},{LARGE_LABEL_MARGIN_DOTS}"
            f"^A0R,{LARGE_DESCRIPTION_FONT_HEIGHT_DOTS},{LARGE_DESCRIPTION_FONT_WIDTH_DOTS}"
            f"^FD{line}^FS"
        )
    payload.extend(
        [
            f"^BY{barcode_module},2,{LARGE_BARCODE_HEIGHT_DOTS}",
            f"^FO{barcode_x},{barcode_y}^BCR,{LARGE_BARCODE_HEIGHT_DOTS},N,N,N^FD{barcode}^FS",
            f"^FO{item_x},{item_y}"
            f"^A0R,{item_font_height},{item_font_width}^FD{item_code}^FS",
            # A second pass offset by two dots gives the distant-reading item
            # code more weight without changing its measured width.
            f"^FO{item_x + 2},{item_y}"
            f"^A0R,{item_font_height},{item_font_width}^FD{item_code}^FS",
            f"^PQ{quantity},0,1,N",
            "^XZ",
        ]
    )
    return "".join(payload).encode("ascii")


@dataclass
class PrintService:
    settings: Settings
    discovery: PrinterDiscovery
    label_builder: Callable[[CatalogItem, int, Settings], bytes] = build_label
    spool_extension: str = "sbpl"

    def print_items(
        self,
        items: list[tuple[CatalogItem, int]],
        source: str,
        reference: str | None,
    ) -> dict:
        payload = b"".join(
            self.label_builder(item, quantity, self.settings) for item, quantity in items
        )
        label_count = sum(quantity for _, quantity in items)
        job_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        self.settings.spool_dir.mkdir(parents=True, exist_ok=True)
        spool_path = self.settings.spool_dir / f"{job_id}.{self.spool_extension}"
        metadata_path = self.settings.spool_dir / f"{job_id}.json"
        spool_path.write_bytes(payload)

        status = "dry-run"
        printer_ip = None
        delivery_metadata = None
        if self.settings.print_enabled:
            delivery = self.discovery.send(payload)
            printer_ip = delivery.ip
            status = "submitted" if delivery.complete else "delivery-uncertain"
            delivery_metadata = {
                "complete": delivery.complete,
                "bytes_sent": delivery.bytes_sent,
                "bytes_total": delivery.bytes_total,
                "attempts": delivery.attempts,
                "elapsed_seconds": round(delivery.elapsed_seconds, 3),
                "error": delivery.error,
            }

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
            "delivery": delivery_metadata,
            "host": socket.gethostname(),
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata

    def print_staff_label(self, name: str, badge_code: str, quantity: int = 1) -> dict:
        item = CatalogItem(
            item_code=badge_code,
            description=f"PRV PICK & PACK STAFF - {name}",
            barcode=badge_code,
        )
        return self.print_items(
            [(item, quantity)],
            source="pickpack-staff",
            reference=name,
        )
