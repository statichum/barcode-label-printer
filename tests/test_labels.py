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
    assert payload.count(ESC + b"RDB01,018,032,Dawnbreaker Frameset - Small") == 2
    assert ESC + b"BG02126>F9412345678901" in payload
    assert b"9412345678901" not in payload.split(ESC + b"BG02126", 1)[0]
    assert ESC + b"Q3" + ESC + b"Z" in payload
    assert payload.index(ESC + b"RDB01,031,065,F") > payload.index(b"9412345678901")


def test_description_uses_dot_based_margins_and_three_larger_lines(tmp_path):
    config = settings(tmp_path)
    description = (
        "W" * 28
        + " "
        + "W" * 28
        + " "
        + "W" * 28
        + " "
        + "SHOULD-NOT-PRINT"
    )
    item = CatalogItem("ITEM-1", description, "9412345678901")

    payload = build_label(item, 1, config)

    assert ESC + b"H0040" + ESC + b"V0010" in payload
    assert payload.count(ESC + b"RDB01,018,032," + b"W" * 28) == 6
    assert ESC + b"V0045" + ESC + b"RDB01,018,032," + b"W" * 28 in payload
    assert ESC + b"V0080" + ESC + b"RDB01,018,032," + b"W" * 28 in payload
    assert b"SHOULD-NOT-PRINT" not in payload


def test_invalid_print_quality_settings_are_rejected(tmp_path):
    item = CatalogItem("ITEM-1", "Example item", "9412345678901")

    with pytest.raises(ValueError, match="PRINTER_PRINT_SPEED"):
        build_label(item, 1, settings(tmp_path, printer_print_speed=5))
    with pytest.raises(ValueError, match="PRINTER_DARKNESS"):
        build_label(item, 1, settings(tmp_path, printer_darkness="6A"))


def test_proportional_description_wrap_uses_available_width_for_narrow_text(tmp_path):
    config = settings(tmp_path)
    description = "i" * 60
    item = CatalogItem("ITEM-1", description, "9412345678901")

    payload = build_label(item, 1, config)

    assert payload.count(ESC + b"RDB01,018,032," + description.encode()) == 2


def test_long_item_code_uses_a_smaller_smooth_font_to_preserve_margins(tmp_path):
    config = settings(tmp_path)
    item_code = "X" * 36
    item = CatalogItem(item_code, "Example item", "9412345678901")

    payload = build_label(item, 1, config)

    assert payload.count(ESC + b"RDB01,014,029,X") == 144


def test_item_code_digits_use_fixed_pitch_and_are_visually_centered(tmp_path):
    config = settings(tmp_path)
    item_code = "TYSSM11159766"
    item = CatalogItem(item_code, "Example item", "9412345678901")

    payload = build_label(item, 1, config)

    assert ESC + b"H0262" + ESC + b"V0276" + ESC + b"RDB01,031,065,1" in payload
    assert ESC + b"H0292" + ESC + b"V0276" + ESC + b"RDB01,031,065,1" in payload
    assert ESC + b"H0322" + ESC + b"V0276" + ESC + b"RDB01,031,065,1" in payload


def test_barcode_moves_up_when_description_uses_fewer_lines(tmp_path):
    config = settings(tmp_path)
    one_line = CatalogItem("ITEM-1", "Short description", "9412345678901")
    three_lines = CatalogItem("ITEM-1", "W" * 84, "9412345678901")

    one_line_payload = build_label(one_line, 1, config)
    three_line_payload = build_label(three_lines, 1, config)

    assert ESC + b"V0085" + ESC + b"BG02126" in one_line_payload
    assert ESC + b"V0127" + ESC + b"BG02126" in three_line_payload


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
