from app.database import CatalogItem
from app.myob import merge_purchase_order


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
    assert "No barcode" in line["warning"]

