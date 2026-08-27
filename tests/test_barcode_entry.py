import time
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app import main
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


def reset_barcode_catalog():
    with main.barcode_admin_lock:
        main.barcode_catalog_cache.update(
            {"items": None, "stored_at": None, "generation": 0}
        )
    main.barcode_stock_cache.update({"quantities": None, "stored_at": None})


def test_barcode_entry_catalogue_is_available_without_a_pin(tmp_path, monkeypatch):
    configured = settings(tmp_path)
    myob = MagicMock()
    myob.list_active_stock_items.return_value = [
        stock_item("ITEM2"),
        stock_item("ITEM10"),
        stock_item(
            "ITEM-X",
            barcode_reference_id="placeholder-xref",
            barcode_reference_value="X",
        ),
    ]
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(main, "myob", myob)
    reset_barcode_catalog()

    response = TestClient(main.app).get("/api/barcode-entry/items?refresh=true")

    assert response.status_code == 200
    assert [item["item_code"] for item in response.json()["items"]] == [
        "ITEM2",
        "ITEM10",
        "ITEM-X",
    ]
    assert all(item["barcode_entry_allowed"] for item in response.json()["items"])
    placeholder = response.json()["items"][2]
    assert placeholder["barcode"] is None
    assert placeholder["warning"] is None
    myob.list_active_stock_items.assert_called_once_with()


def test_barcode_entry_rechecks_replaces_x_and_verifies_without_a_pin(
    tmp_path, monkeypatch
):
    configured = settings(tmp_path, barcode_assignment_enabled=True)
    placeholder = stock_item(
        "NEW",
        barcode_reference_id="placeholder-xref",
        barcode_reference_value="x",
    )
    verified = stock_item(
        "NEW",
        barcode="012345678905",
        barcode_reference_id="new-xref",
        barcode_reference_value="012345678905",
    )
    myob = MagicMock()
    myob.get_assignment_stock_items.side_effect = [
        {"NEW": placeholder},
        {"NEW": verified},
    ]
    update_catalog = MagicMock()
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(main, "myob", myob)
    monkeypatch.setattr(main, "load_assignment_catalog", lambda: ([placeholder], 1.0))
    monkeypatch.setattr(main, "update_stored_assignment_catalog", update_catalog)

    response = TestClient(main.app).post(
        "/api/barcode-entry/commit",
        json={"entries": [{"item_code": "new", "barcode": "012345678905"}]},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["written_count"] == 1
    myob.assign_barcode.assert_called_once_with(
        "NEW", "012345678905", "placeholder-xref"
    )
    update_catalog.assert_called_once_with({"NEW": verified})


def test_barcode_entry_can_replace_an_existing_real_barcode(tmp_path, monkeypatch):
    configured = settings(tmp_path, barcode_assignment_enabled=True)
    existing = stock_item(
        "EXISTING",
        barcode="9412345678901",
        barcode_reference_id="existing-xref",
        barcode_reference_value="9412345678901",
    )
    verified = stock_item(
        "EXISTING",
        barcode="012345678905",
        barcode_reference_id="replacement-xref",
        barcode_reference_value="012345678905",
    )
    myob = MagicMock()
    myob.get_assignment_stock_items.side_effect = [
        {"EXISTING": existing},
        {"EXISTING": verified},
    ]
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(main, "myob", myob)
    monkeypatch.setattr(main, "load_assignment_catalog", lambda: ([existing], 1.0))
    monkeypatch.setattr(main, "update_stored_assignment_catalog", MagicMock())

    response = TestClient(main.app).post(
        "/api/barcode-entry/commit",
        json={
            "entries": [
                {"item_code": "EXISTING", "barcode": "012345678905"}
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["entered"][0]["action"] == "replace"
    assert response.json()["entered"][0]["previous_barcode"] == "9412345678901"
    myob.assign_barcode.assert_called_once_with(
        "EXISTING", "012345678905", "existing-xref"
    )


def test_barcode_entry_rejects_a_catalogue_collision_before_writing(
    tmp_path, monkeypatch
):
    configured = settings(tmp_path, barcode_assignment_enabled=True)
    target = stock_item("TARGET")
    owner = stock_item(
        "OWNER",
        barcode="012345678905",
        barcode_reference_id="owner-xref",
        barcode_reference_value="012345678905",
    )
    myob = MagicMock()
    myob.get_assignment_stock_items.return_value = {"TARGET": target}
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(main, "myob", myob)
    monkeypatch.setattr(main, "load_assignment_catalog", lambda: ([target, owner], 1.0))

    response = TestClient(main.app).post(
        "/api/barcode-entry/commit",
        json={"entries": [{"item_code": "TARGET", "barcode": "012345678905"}]},
    )

    assert response.status_code == 409
    assert "already used by OWNER" in response.json()["detail"]
    myob.assign_barcode.assert_not_called()


def test_barcode_entry_respects_the_existing_write_enable_switch(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        main, "settings", settings(tmp_path, barcode_assignment_enabled=False)
    )

    response = TestClient(main.app).post(
        "/api/barcode-entry/commit",
        json={"entries": [{"item_code": "TARGET", "barcode": "012345678905"}]},
    )

    assert response.status_code == 503
    assert "BARCODE_ASSIGNMENT_ENABLED=true" in response.json()["detail"]


def test_barcode_entry_stock_is_only_refreshed_on_request_and_then_stored(
    tmp_path, monkeypatch
):
    configured = settings(tmp_path)
    item = stock_item("ITEM1")
    myob = MagicMock()
    myob.get_main_qty_on_hand.return_value = {"ITEM1": 7}
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(main, "myob", myob)
    monkeypatch.setattr(
        main, "load_assignment_catalog", lambda refresh=False: ([item], 100.0)
    )
    reset_barcode_catalog()
    client = TestClient(main.app)

    initial = client.get("/api/barcode-entry/items")

    assert initial.status_code == 200
    assert initial.json()["items"][0]["stock_on_hand"] is None
    assert initial.json()["stock_stored_at"] is None
    myob.get_main_qty_on_hand.assert_not_called()

    refreshed = client.post("/api/barcode-entry/stock-on-hand/refresh")

    assert refreshed.status_code == 200
    assert refreshed.json()["quantities"] == {"ITEM1": 7}
    myob.get_main_qty_on_hand.assert_called_once_with(["ITEM1"])
    assert (configured.data_dir / "barcode-stock-on-hand.json").is_file()

    main.barcode_stock_cache.update({"quantities": None, "stored_at": None})
    myob.get_main_qty_on_hand.reset_mock()
    stored = client.get("/api/barcode-entry/items")

    assert stored.json()["items"][0]["stock_on_hand"] == 7
    assert stored.json()["stock_stored_at"] == refreshed.json()["stored_at"]
    assert stored.json()["stock_cache_fresh"] is True
    myob.get_main_qty_on_hand.assert_not_called()

    main.barcode_stock_cache.update(
        {
            "quantities": {"ITEM1": 7},
            "stored_at": time.time() - main.BARCODE_STOCK_CACHE_SECONDS - 1,
        }
    )
    expired = client.get("/api/barcode-entry/items")

    assert expired.json()["items"][0]["stock_on_hand"] is None
    assert expired.json()["stock_cache_fresh"] is False
    myob.get_main_qty_on_hand.assert_not_called()
