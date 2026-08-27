import pytest
from pydantic import ValidationError

from app.models import (
    BarcodeAdminLoginRequest,
    BarcodeAssignmentPreviewRequest,
    BarcodeEntryCommitRequest,
    BarcodeEntryItemRequest,
    ManualItemLookupRequest,
    PrintItemRequest,
    PrintRequest,
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


def test_barcode_assignment_request_accepts_unlocked_catalogue_size():
    request = BarcodeAssignmentPreviewRequest(
        item_codes=[f"ITEM{index}" for index in range(351)]
    )

    assert len(request.item_codes) == 351
    with pytest.raises(ValidationError):
        BarcodeAssignmentPreviewRequest(
            item_codes=[f"ITEM{index}" for index in range(20_001)]
        )


def test_print_job_accepts_350_item_rows():
    request = PrintRequest(
        items=[
            PrintItemRequest(item_code=f"ITEM{index}", quantity=1)
            for index in range(350)
        ]
    )

    assert len(request.items) == 350
    with pytest.raises(ValidationError):
        PrintRequest(
            items=[
                PrintItemRequest(item_code=f"ITEM{index}", quantity=1)
                for index in range(351)
            ]
        )


def test_barcode_admin_pin_requires_digits():
    request = BarcodeAdminLoginRequest(pin="2468")

    assert request.pin == "2468"


def test_entered_barcode_preserves_leading_zeroes_and_normalizes_item_code():
    request = BarcodeEntryItemRequest(
        item_code=" product-1 ", barcode=" 012345678905 "
    )

    assert request.item_code == "PRODUCT-1"
    assert request.barcode == "012345678905"


def test_entered_barcode_batch_rejects_duplicate_items_and_barcodes():
    with pytest.raises(ValidationError, match="Each item may appear only once"):
        BarcodeEntryCommitRequest(
            entries=[
                BarcodeEntryItemRequest(item_code="ITEM1", barcode="012345678905"),
                BarcodeEntryItemRequest(item_code="item1", barcode="9412345678901"),
            ]
        )
    with pytest.raises(ValidationError, match="Each scanned barcode"):
        BarcodeEntryCommitRequest(
            entries=[
                BarcodeEntryItemRequest(item_code="ITEM1", barcode="ABC-1234"),
                BarcodeEntryItemRequest(item_code="ITEM2", barcode="abc-1234"),
            ]
        )
