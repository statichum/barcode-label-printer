from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app import main
from app.database import CatalogItem
from app.myob import ean13_internal_barcode
from tests.helpers import settings


def stock_item(
    item_code: str,
    *,
    barcode: str | None = None,
    barcode_reference_id: str | None = None,
    barcode_reference_value: str | None = None,
):
    return {
        "item_code": item_code,
        "description": f"Description for {item_code}",
        "barcode": barcode,
        "barcode_reference_id": barcode_reference_id,
        "barcode_reference_value": barcode_reference_value,
        "barcode_reference_count": 1 if barcode_reference_id else 0,
        "status": "Active",
        "alternate_ids": {barcode_reference_value} if barcode_reference_value else set(),
    }


def test_pin_protected_preview_rechecks_and_updates_existing_x_row(tmp_path, monkeypatch):
    configured = settings(
        tmp_path,
        barcode_admin_pin="2468",
        barcode_assignment_enabled=True,
    )
    myob = MagicMock()
    catalog = [
        stock_item(
            "OLD",
            barcode=ean13_internal_barcode(8),
            barcode_reference_id="old-xref",
            barcode_reference_value=ean13_internal_barcode(8),
        ),
        stock_item(
            "NEW",
            barcode_reference_id="placeholder-xref",
            barcode_reference_value="x",
        ),
    ]
    myob.list_stock_items.return_value = catalog
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(main, "myob", myob)
    main.barcode_admin_sessions.clear()
    main.barcode_assignment_previews.clear()

    client = TestClient(main.app)
    login = client.post("/api/barcode-admin/login", json={"pin": "2468"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']}"}

    preview = client.post(
        "/api/barcode-admin/assignments/preview",
        headers=headers,
        json={"item_codes": ["NEW"]},
    )
    assert preview.status_code == 200
    assignment = preview.json()["assignments"][0]
    assert assignment["action"] == "replace"
    assert assignment["previous_barcode"] == "x"
    assert assignment["cross_reference_id"] == "placeholder-xref"

    myob.get_stock_items.return_value = {
        "NEW": CatalogItem("NEW", "Description for NEW", assignment["barcode"])
    }
    committed = client.post(
        "/api/barcode-admin/assignments/commit",
        headers=headers,
        json={"preview_token": preview.json()["preview_token"]},
    )

    assert committed.status_code == 200
    myob.assign_barcode.assert_called_once_with(
        "NEW", assignment["barcode"], "placeholder-xref"
    )


def test_barcode_admin_rejects_wrong_pin(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "settings", settings(tmp_path, barcode_admin_pin="2468"))
    client = TestClient(main.app)

    response = client.post("/api/barcode-admin/login", json={"pin": "9999"})

    assert response.status_code == 401
