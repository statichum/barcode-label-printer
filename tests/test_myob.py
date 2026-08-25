import httpx

from app.database import CatalogItem
from app.myob import (
    MyobClient,
    ean13_internal_barcode,
    internal_barcode_sequence,
    merge_catalog_items,
    merge_purchase_order,
    plan_barcode_assignments,
    stock_item_from_myob,
    validate_barcode_assignments,
)
from tests.helpers import settings


def field(value):
    return {"value": value}


def test_purchase_order_lines_are_enriched_from_syncer_catalog():
    order = {
        "OrderNbr": field("000796"),
        "Date": field("2026-08-24T00:00:00+00:00"),
        "Details": [
            {
                "LineNbr": field(1),
                "InventoryID": field("FXL9301-00067"),
                "LineDescription": field("MYOB description"),
                "OrderQty": field(2),
            }
        ],
    }
    catalog = {
        "FXL9301-00067": CatalogItem(
            "FXL9301-00067", "Database description", "9412345678901"
        )
    }

    result = merge_purchase_order(order, catalog)

    assert result["po_number"] == "000796"
    assert result["lines"][0] == {
        "line_number": 1,
        "po_position": 0,
        "item_code": "FXL9301-00067",
        "description": "Database description",
        "barcode": "9412345678901",
        "quantity": 2,
        "selected": True,
        "printable": True,
        "warning": None,
    }


def test_missing_catalog_item_is_visible_but_not_selected():
    order = {
        "OrderNbr": field("000796"),
        "Details": [
            {
                "InventoryID": field("MISSING-1"),
                "LineDescription": field("Still show this line"),
                "OrderQty": field(1),
            }
        ],
    }

    line = merge_purchase_order(order, {})["lines"][0]

    assert line["description"] == "Still show this line"
    assert line["selected"] is False
    assert line["printable"] is False
    assert "barcode cross-reference" in line["warning"]


def test_stock_item_barcode_comes_from_myob_cross_references():
    item = stock_item_from_myob(
        {
            "InventoryID": field("BEEN1000"),
            "Description": field("Been Bar Tape"),
            "CrossReferences": [
                {
                    "AlternateType": field("Vendor Part Number"),
                    "AlternateID": field("IGNORE-ME"),
                },
                {
                    "AlternateType": field("Barcode"),
                    "AlternateID": field("0400000001821"),
                },
            ],
        }
    )

    assert item == CatalogItem("BEEN1000", "Been Bar Tape", "0400000001821")


def test_syncer_description_is_kept_but_its_barcode_is_never_used():
    database_items = {
        "BEEN1000": CatalogItem("BEEN1000", "Syncer description", "STALE-BARCODE")
    }
    myob_items = {
        "BEEN1000": CatalogItem("BEEN1000", "MYOB description", "0400000001821")
    }

    merged = merge_catalog_items(["BEEN1000"], database_items, myob_items)

    assert merged["BEEN1000"] == CatalogItem(
        "BEEN1000", "Syncer description", "0400000001821"
    )


def test_myob_x_barcode_is_treated_as_missing():
    item = stock_item_from_myob(
        {
            "InventoryID": field("BEEN1000"),
            "Description": field("Been Bar Tape"),
            "CrossReferences": [
                {
                    "AlternateType": field("Barcode"),
                    "AlternateID": field("x"),
                }
            ],
        }
    )

    assert item.barcode is None


def test_real_barcode_after_x_placeholder_is_used():
    item = stock_item_from_myob(
        {
            "InventoryID": field("BEEN1000"),
            "Description": field("Been Bar Tape"),
            "CrossReferences": [
                {"AlternateType": field("Barcode"), "AlternateID": field("x")},
                {
                    "AlternateType": field("Barcode"),
                    "AlternateID": field("0400000000015"),
                },
            ],
        }
    )

    assert item.barcode == "0400000000015"


def test_internal_barcode_formula_matches_ean13_sequence():
    assert ean13_internal_barcode(1) == "0400000000015"
    assert ean13_internal_barcode(182) == "0400000001821"
    assert internal_barcode_sequence("0400000001821") == 182
    assert internal_barcode_sequence("0400000001823") is None


def test_assignment_plan_starts_after_highest_used_internal_barcode():
    stock_items = [
        {
            "item_code": "OLD",
            "description": "Old item",
            "barcode": ean13_internal_barcode(8),
            "status": "Active",
            "alternate_ids": {ean13_internal_barcode(8)},
        },
        {
            "item_code": "NEW2",
            "description": "Second new item",
            "barcode": None,
            "status": "Active",
            "alternate_ids": {"SUP-2"},
        },
        {
            "item_code": "NEW10",
            "description": "Tenth new item",
            "barcode": None,
            "status": "Active",
            "alternate_ids": set(),
        },
    ]

    assignments = plan_barcode_assignments(["NEW2", "NEW10"], stock_items)

    assert [item["barcode"] for item in assignments] == [
        ean13_internal_barcode(9),
        ean13_internal_barcode(10),
    ]
    validate_barcode_assignments(assignments, stock_items)


def test_assignment_plan_replaces_existing_barcode_row():
    stock_items = [
        {
            "item_code": "OLD",
            "description": "Old item",
            "barcode": "9412345678901",
            "barcode_reference_id": "xref-id",
            "barcode_reference_value": "9412345678901",
            "barcode_reference_count": 1,
            "status": "Active",
            "alternate_ids": {"9412345678901"},
        }
    ]

    assignments = plan_barcode_assignments(["OLD"], stock_items)

    assert assignments[0]["action"] == "replace"
    assert assignments[0]["cross_reference_id"] == "xref-id"
    assert assignments[0]["previous_barcode"] == "9412345678901"


def test_stock_item_lookup_calls_myob_with_cross_references(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/entity/auth/login":
            return httpx.Response(204)
        return httpx.Response(
            200,
            json=[
                {
                    "InventoryID": field("BEEN1000"),
                    "Description": field("Been Bar Tape"),
                    "CrossReferences": [
                        {
                            "AlternateType": field("Barcode"),
                            "AlternateID": field("0400000001821"),
                        }
                    ],
                }
            ],
        )

    client = MyobClient(settings(tmp_path))
    client._client.close()
    client._client = httpx.Client(
        base_url="https://example.invalid",
        transport=httpx.MockTransport(handler),
    )

    items = client.get_stock_items(["been1000"])
    client._client.close()

    stock_request = requests[-1]
    assert stock_request.url.path.endswith("/StockItem")
    assert stock_request.url.params["$expand"] == "CrossReferences"
    assert stock_request.url.params["$filter"] == "InventoryID eq 'BEEN1000'"
    assert items["BEEN1000"].barcode == "0400000001821"


def test_active_stock_item_catalog_uses_paging_and_cross_references(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/entity/auth/login":
            return httpx.Response(204)
        skip = int(request.url.params["$skip"])
        if skip == 0:
            return httpx.Response(
                200,
                json=[
                    {
                        "InventoryID": field("NEW1"),
                        "Description": field("New item"),
                        "ItemStatus": field("Active"),
                        "CrossReferences": [],
                    }
                ],
            )
        return httpx.Response(200, json=[])

    client = MyobClient(settings(tmp_path))
    client._client.close()
    client._client = httpx.Client(
        base_url="https://example.invalid",
        transport=httpx.MockTransport(handler),
    )

    items = client.list_active_stock_items()
    client._client.close()

    request = requests[-1]
    assert request.url.params["$filter"] == "ItemStatus eq 'Active'"
    assert request.url.params["$expand"] == "CrossReferences"
    assert items[0]["item_code"] == "NEW1"
    assert items[0]["barcode"] is None


def test_barcode_assignment_put_deletes_and_recreates_existing_barcode_row(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/entity/auth/login":
            return httpx.Response(204)
        return httpx.Response(200, json={})

    client = MyobClient(settings(tmp_path))
    client._client.close()
    client._client = httpx.Client(
        base_url="https://example.invalid",
        transport=httpx.MockTransport(handler),
    )

    client.assign_barcode("NEW1", "0400000000015", "xref-id")
    client._client.close()

    request = requests[-1]
    assert request.method == "PUT"
    assert request.url.path.endswith("/StockItem")
    assert request.read().decode() == (
        '{"InventoryID":{"value":"NEW1"},"CrossReferences":'
        '[{"id":"xref-id","delete":true},'
        '{"AlternateID":{"value":"0400000000015"},'
        '"AlternateType":{"value":"Barcode"},"UOM":{"value":"EACH"}}]}'
    )


def test_barcode_assignment_put_creates_row_when_none_exists(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/entity/auth/login":
            return httpx.Response(204)
        return httpx.Response(200, json={})

    client = MyobClient(settings(tmp_path))
    client._client.close()
    client._client = httpx.Client(
        base_url="https://example.invalid",
        transport=httpx.MockTransport(handler),
    )

    client.assign_barcode("NEW1", "0400000000015")
    client._client.close()

    assert requests[-1].read().decode() == (
        '{"InventoryID":{"value":"NEW1"},"CrossReferences":['
        '{"AlternateID":{"value":"0400000000015"},'
        '"AlternateType":{"value":"Barcode"},"UOM":{"value":"EACH"}}]}'
    )


def test_main_qty_available_uses_web_ninja_inventory_and_filters_selected_items(
    tmp_path,
):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/entity/auth/login":
            return httpx.Response(204)
        return httpx.Response(
            200,
            json={
                "Result": [
                    {
                        "InventoryID": field("NEW1"),
                        "Warehouse": field("MAIN"),
                        "QtyAvailable": field(12),
                    },
                    {
                        "InventoryID": field("NEW1"),
                        "Warehouse": field("INTR"),
                        "QtyAvailable": field(99),
                    },
                    {
                        "InventoryID": field("OTHER"),
                        "Warehouse": field("MAIN"),
                        "QtyAvailable": field(50),
                    },
                ]
            },
        )

    client = MyobClient(settings(tmp_path))
    client._client.close()
    client._client = httpx.Client(
        base_url="https://example.invalid",
        transport=httpx.MockTransport(handler),
    )

    quantities = client.get_main_qty_available(["new1", "missing"])
    client._client.close()

    assert quantities == {"NEW1": 12, "MISSING": 0}
    request = requests[-1]
    assert request.method == "PUT"
    assert request.url.path.endswith("/WebNinjaInventory")
    assert request.url.params["$expand"] == "Result"
    assert request.read().decode() == '{"Result":[]}'
