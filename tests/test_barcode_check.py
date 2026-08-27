from fastapi.testclient import TestClient

from app import main


def stock_item(
    item_code: str,
    *,
    barcode_ids: set[str] | None = None,
    supplier_codes: set[str] | None = None,
    alternate_ids: set[str] | None = None,
):
    barcode_ids = barcode_ids or set()
    supplier_codes = supplier_codes or set()
    return {
        "item_code": item_code,
        "description": f"Description for {item_code}",
        "barcode": next(iter(barcode_ids), None),
        "barcode_reference_id": None,
        "barcode_reference_value": next(iter(barcode_ids), None),
        "barcode_reference_count": len(barcode_ids),
        "status": "Active",
        "alternate_ids": alternate_ids or barcode_ids | supplier_codes,
        "barcode_ids": barcode_ids,
        "supplier_codes": supplier_codes,
    }


def test_barcode_check_returns_item_description_and_supplier_code(monkeypatch):
    item = stock_item(
        "BEEN1000",
        barcode_ids={"9412345678901"},
        supplier_codes={"SUP-1000"},
    )
    monkeypatch.setattr(main, "load_assignment_catalog", lambda: ([item], 123.0))

    response = TestClient(main.app).post(
        "/api/barcodes/check", json={"barcode": "9412345678901"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "found": True,
        "barcode": "9412345678901",
        "item_code": "BEEN1000",
        "description": "Description for BEEN1000",
        "supplier_codes": ["SUP-1000"],
        "stored_at": 123.0,
    }


def test_barcode_check_does_not_match_supplier_cross_references(monkeypatch):
    item = stock_item(
        "BEEN1000",
        barcode_ids={"9412345678901"},
        supplier_codes={"SUP-1000"},
    )
    monkeypatch.setattr(main, "load_assignment_catalog", lambda: ([item], 123.0))

    response = TestClient(main.app).post(
        "/api/barcodes/check", json={"barcode": "SUP-1000"}
    )

    assert response.status_code == 200
    assert response.json()["found"] is False


def test_barcode_check_warns_when_barcode_has_multiple_items(monkeypatch):
    items = [
        stock_item("ITEM2", barcode_ids={"9412345678901"}),
        stock_item("ITEM1", barcode_ids={"9412345678901"}),
    ]
    monkeypatch.setattr(main, "load_assignment_catalog", lambda: (items, 123.0))

    response = TestClient(main.app).post(
        "/api/barcodes/check", json={"barcode": "9412345678901"}
    )

    assert response.status_code == 409
    assert "linked to multiple MYOB items: ITEM1, ITEM2" in response.json()["detail"]


def test_barcode_check_uses_non_barcode_cross_references_for_old_supplier_cache(
    monkeypatch,
):
    item = stock_item(
        "LEGACY",
        barcode_ids={"9412345678901"},
        alternate_ids={"9412345678901", "OLD-SUPPLIER-CODE"},
    )
    item.pop("supplier_codes")
    monkeypatch.setattr(main, "load_assignment_catalog", lambda: ([item], 123.0))

    response = TestClient(main.app).post(
        "/api/barcodes/check", json={"barcode": "9412345678901"}
    )

    assert response.status_code == 200
    assert response.json()["supplier_codes"] == ["OLD-SUPPLIER-CODE"]
