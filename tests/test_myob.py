import httpx

from app.database import CatalogItem
from app.myob import (
    MyobClient,
    merge_catalog_items,
    merge_purchase_order,
    stock_item_from_myob,
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
