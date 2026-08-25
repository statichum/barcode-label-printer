from app.models import (
    BarcodeAdminLoginRequest,
    BarcodeAssignmentPreviewRequest,
    ManualItemLookupRequest,
    PrintItemRequest,
    StaffLabelPrintRequest,
)


def test_manual_item_codes_are_normalized_to_uppercase_and_deduplicated():
    request = ManualItemLookupRequest(item_codes=[" been1000 ", "BEEN1000"])

    assert request.item_codes == ["BEEN1000"]


def test_print_item_code_is_normalized_to_uppercase():
    request = PrintItemRequest(item_code=" been1000 ", quantity=1)

    assert request.item_code == "BEEN1000"


def test_staff_label_request_normalizes_badge_and_name():
    request = StaffLabelPrintRequest(
        name="  Chris   Tuckey ", badge_code="ppu-7k4m-92qx", quantity=2
    )

    assert request.name == "Chris Tuckey"
    assert request.badge_code == "PPU-7K4M-92QX"


def test_barcode_assignment_codes_are_normalized_and_deduplicated():
    request = BarcodeAssignmentPreviewRequest(item_codes=[" new2 ", "NEW2", "new10"])

    assert request.item_codes == ["NEW2", "NEW10"]


def test_barcode_admin_pin_requires_digits():
    request = BarcodeAdminLoginRequest(pin="2468")

    assert request.pin == "2468"
