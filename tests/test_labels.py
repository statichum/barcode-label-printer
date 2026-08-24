from app.database import CatalogItem
import pytest

from app.labels import ESC, PrintService, build_label, safe_barcode, safe_sbpl_text
from app.printer import PrinterDiscovery
from tests.helpers import settings


def test_build_label_uses_50_by_30_mm_at_305_dpi(tmp_path):
    config = settings(tmp_path)
    item = CatalogItem("FXL9301-00067", "Dawnbreaker Frameset - Small", "9412345678901")

    payload = build_label(item, 3, config)

    assert payload.startswith(ESC + b"A" + ESC + b"A103600600")
    assert ESC + b"S" + b"Dawnbreaker Frameset - Small" in payload
    assert ESC + b"BG03250>F9412345678901" in payload
    assert b"9412345678901" not in payload.split(ESC + b"BG03250", 1)[0]
    assert ESC + b"Q3" + ESC + b"Z" in payload
    assert payload.index(b"FXL9301-00067") > payload.index(b"9412345678901")


def test_description_is_cut_off_after_two_tightly_spaced_small_lines(tmp_path):
    config = settings(tmp_path)
    description = "A" * 72 + " " + "B" * 72 + " " + "SHOULD-NOT-PRINT"
    item = CatalogItem("ITEM-1", description, "9412345678901")

    payload = build_label(item, 1, config)

    assert ESC + b"V0008" + ESC + b"L0101" + ESC + b"S" + b"A" * 72 in payload
    assert ESC + b"V0025" + ESC + b"S" + b"B" * 72 in payload
    assert b"SHOULD-NOT-PRINT" not in payload


def test_text_cannot_inject_sbpl_commands():
    assert safe_sbpl_text("Safe\x1bZ text") == "SafeZ text"


def test_barcode_rejects_sbpl_control_syntax_and_oversized_values():
    with pytest.raises(ValueError):
        safe_barcode("123>F456")
    with pytest.raises(ValueError):
        safe_barcode("1" * 25)


def test_dry_run_spools_without_contacting_printer(tmp_path):
    config = settings(tmp_path, print_enabled=False)
    discovery = PrinterDiscovery(config)
    item = CatalogItem("ABC-1", "Example item", "1234567890123")

    result = PrintService(config, discovery).print_items(
        [(item, 2)], source="manual", reference=None
    )

    assert result["status"] == "dry-run"
    assert result["label_count"] == 2
    assert (config.spool_dir / f"{result['job_id']}.sbpl").exists()
    assert (config.spool_dir / f"{result['job_id']}.json").exists()
