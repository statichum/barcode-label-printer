from app.models import ManualItemLookupRequest, PrintItemRequest


def test_manual_item_codes_are_normalized_to_uppercase_and_deduplicated():
    request = ManualItemLookupRequest(item_codes=[" been1000 ", "BEEN1000"])

    assert request.item_codes == ["BEEN1000"]


def test_print_item_code_is_normalized_to_uppercase():
    request = PrintItemRequest(item_code=" been1000 ", quantity=1)

    assert request.item_code == "BEEN1000"
