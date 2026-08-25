import threading
import time
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app import main
from app.myob import ean13_internal_barcode
from tests.helpers import settings


def reset_barcode_catalog():
    with main.barcode_admin_lock:
        main.barcode_catalog_cache.update(
            {"items": None, "stored_at": None, "generation": 0}
        )


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
    myob.list_active_stock_items.return_value = catalog
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(main, "myob", myob)
    main.barcode_admin_sessions.clear()
    main.barcode_assignment_previews.clear()
    reset_barcode_catalog()

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

    myob.get_assignment_stock_items.return_value = {
        "NEW": stock_item(
            "NEW",
            barcode=assignment["barcode"],
            barcode_reference_id="new-placeholder-xref",
            barcode_reference_value=assignment["barcode"],
        )
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
    myob.list_active_stock_items.assert_called_once_with()

    myob.get_main_qty_available.return_value = {"NEW": 7}
    stock_labels = client.post(
        "/api/barcode-admin/stock-labels",
        headers=headers,
        json={"item_codes": ["NEW"]},
    )

    assert stock_labels.status_code == 200
    assert stock_labels.json()["items"][0] == {
        "item_code": "NEW",
        "description": "Description for NEW",
        "barcode": assignment["barcode"],
        "quantity": 7,
        "qty_available": 7,
        "selected": True,
        "printable": True,
        "warning": None,
    }


def test_barcode_admin_rejects_wrong_pin(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "settings", settings(tmp_path, barcode_admin_pin="2468"))
    client = TestClient(main.app)

    response = client.post("/api/barcode-admin/login", json={"pin": "9999"})

    assert response.status_code == 401


def test_assignment_catalog_is_stored_and_reused_after_memory_is_cleared(
    tmp_path, monkeypatch
):
    configured = settings(tmp_path)
    myob = MagicMock()
    myob.list_active_stock_items.return_value = [
        stock_item("NEW", barcode_reference_id="placeholder", barcode_reference_value="x")
    ]
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(main, "myob", myob)
    reset_barcode_catalog()

    first_items, first_stored_at = main.load_assignment_catalog()

    assert first_items[0]["item_code"] == "NEW"
    assert first_items[0]["barcode_reference_value"] == "x"
    assert (configured.data_dir / "barcode-stock-items.json").is_file()
    myob.list_active_stock_items.assert_called_once_with()

    reset_barcode_catalog()
    myob.list_active_stock_items.reset_mock()
    second_items, second_stored_at = main.load_assignment_catalog()

    assert second_items == first_items
    assert second_stored_at == first_stored_at
    myob.list_active_stock_items.assert_not_called()


def test_overlapping_catalog_refreshes_share_one_myob_load(tmp_path, monkeypatch):
    configured = settings(tmp_path)
    myob = MagicMock()
    started = threading.Event()
    release = threading.Event()

    def slow_load():
        started.set()
        assert release.wait(timeout=2)
        return [stock_item("NEW")]

    myob.list_active_stock_items.side_effect = slow_load
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(main, "myob", myob)
    reset_barcode_catalog()
    results = []

    first = threading.Thread(
        target=lambda: results.append(main.load_assignment_catalog(refresh=True))
    )
    second = threading.Thread(
        target=lambda: results.append(main.load_assignment_catalog(refresh=True))
    )
    first.start()
    assert started.wait(timeout=2)
    second.start()
    time.sleep(0.05)
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert myob.list_active_stock_items.call_count == 1
    assert len(results) == 2
    assert results[0] == results[1]
