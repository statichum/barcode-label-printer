from app.database import CatalogItem
import pytest

from app.labels import ESC, PrintService, build_label, safe_barcode, safe_sbpl_text
from app.printer import PrinterDiscovery
from tests.helpers import settings


def test_build_label_uses_50_by_30_mm_at_305_dpi(tmp_path):
    config = settings(tmp_path)
    item = CatalogItem("FXL9301-00067", "Dawnbreaker Frameset - Small", "9412345678901")

    payload = build_label(item, 3, config)

    assert payload.startswith(
        ESC + b"A" + ESC + b"CS2" + ESC + b"#E4A" + ESC + b"A103600600"
    )
    assert ESC + b"RDB01,016,025,Dawnbreaker Frameset - Small" in payload
    assert ESC + b"BG02190>F9412345678901" in payload
    assert b"9412345678901" not in payload.split(ESC + b"BG02190", 1)[0]
    assert ESC + b"Q3" + ESC + b"Z" in payload
    assert payload.index(b"FXL9301-00067") > payload.index(b"9412345678901")
    assert ESC + b"V0296" + ESC + b"L0303" + ESC + b"SFXL9301-00067" in payload


def test_description_uses_dot_based_margins_and_three_larger_lines(tmp_path):
    config = settings(tmp_path)
    description = (
        "A" * 33
        + " "
        + "B" * 33
        + " "
        + "C" * 33
        + " "
        + "SHOULD-NOT-PRINT"
    )
    item = CatalogItem("ITEM-1", description, "9412345678901")

    payload = build_label(item, 1, config)

    assert ESC + b"H0032" + ESC + b"V0008" in payload
    assert ESC + b"RDB01,016,025," + b"A" * 33 in payload
    assert ESC + b"V0034" + ESC + b"RDB01,016,025," + b"B" * 33 in payload
    assert ESC + b"V0060" + ESC + b"RDB01,016,025," + b"C" * 33 in payload
    assert b"SHOULD-NOT-PRINT" not in payload


def test_invalid_print_quality_settings_are_rejected(tmp_path):
    item = CatalogItem("ITEM-1", "Example item", "9412345678901")

    with pytest.raises(ValueError, match="PRINTER_PRINT_SPEED"):
        build_label(item, 1, settings(tmp_path, printer_print_speed=5))
    with pytest.raises(ValueError, match="PRINTER_DARKNESS"):
        build_label(item, 1, settings(tmp_path, printer_darkness="6A"))


def test_long_item_code_uses_a_font_that_preserves_side_margins(tmp_path):
    config = settings(tmp_path)
    item_code = "X" * 36
    item = CatalogItem(item_code, "Example item", "9412345678901")

    payload = build_label(item, 1, config)

    assert ESC + b"L0101" + ESC + b"M" + item_code.encode() in payload


def test_medium_item_code_steps_down_to_preserve_side_margins(tmp_path):
    config = settings(tmp_path)
    item_code = "X" * 23
    item = CatalogItem(item_code, "Example item", "9412345678901")

    payload = build_label(item, 1, config)

    assert ESC + b"L0202" + ESC + b"S" + item_code.encode() in payload


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
