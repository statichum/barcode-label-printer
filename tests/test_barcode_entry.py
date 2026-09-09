import json
import threading
import time
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app import main
from app.models import BarcodeEntryCommitRequest
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
    with main.stock_refresh_jobs_lock:
        main.stock_refresh_jobs.clear()


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
    assert response.json()["detail"] == {
        "code": "barcode_ownership_conflict",
        "message": "1 barcode clashes with another MYOB item",
        "conflicts": [
            {
                "barcode": "012345678905",
                "item_code": "TARGET",
                "owner_item_codes": ["OWNER"],
            }
        ],
    }
    myob.assign_barcode.assert_not_called()


def test_barcode_entry_can_confirm_removal_from_the_wrong_owner(
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
    verified_target = stock_item(
        "TARGET",
        barcode="012345678905",
        barcode_reference_id="target-xref",
        barcode_reference_value="012345678905",
    )
    verified_owner = stock_item("OWNER")
    myob = MagicMock()
    myob.get_assignment_stock_items.side_effect = [
        {"TARGET": target, "OWNER": owner},
        {"TARGET": verified_target, "OWNER": verified_owner},
    ]
    update_catalog = MagicMock()
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(main, "myob", myob)
    monkeypatch.setattr(
        main,
        "load_assignment_catalog",
        lambda: ([target, owner], 1.0),
    )
    monkeypatch.setattr(main, "update_stored_assignment_catalog", update_catalog)

    response = TestClient(main.app).post(
        "/api/barcode-entry/commit",
        json={
            "entries": [
                {"item_code": "TARGET", "barcode": "012345678905"}
            ],
            "reassignments": [
                {
                    "item_code": "TARGET",
                    "barcode": "012345678905",
                    "from_item_code": "OWNER",
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["reassigned_count"] == 1
    myob.remove_barcode.assert_called_once_with("OWNER", "owner-xref")
    myob.assign_barcode.assert_called_once_with(
        "TARGET", "012345678905", None
    )
    update_catalog.assert_called_once_with(
        {"TARGET": verified_target, "OWNER": verified_owner}
    )


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
    myob.get_main_qty_available.return_value = {"ITEM1": 7}
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
    myob.get_main_qty_available.assert_not_called()

    refreshed = client.post("/api/barcode-entry/stock-on-hand/refresh")

    assert refreshed.status_code == 200
    assert refreshed.json()["quantities"] == {"ITEM1": 7}
    myob.get_main_qty_available.assert_called_once_with(["ITEM1"])
    assert (configured.data_dir / "barcode-stock-on-hand.json").is_file()
    snapshot = json.loads(
        (configured.data_dir / "barcode-stock-on-hand.json").read_text()
    )
    assert snapshot["version"] == 2

    main.barcode_stock_cache.update({"quantities": None, "stored_at": None})
    myob.get_main_qty_available.reset_mock()
    stored = client.get("/api/barcode-entry/items")

    assert stored.json()["items"][0]["stock_on_hand"] == 7
    assert stored.json()["stock_stored_at"] == refreshed.json()["stored_at"]
    assert stored.json()["stock_cache_fresh"] is True
    myob.get_main_qty_available.assert_not_called()

    main.barcode_stock_cache.update(
        {
            "quantities": {"ITEM1": 7},
            "stored_at": time.time() - main.BARCODE_STOCK_CACHE_SECONDS - 1,
        }
    )
    expired = client.get("/api/barcode-entry/items")

    assert expired.json()["items"][0]["stock_on_hand"] is None
    assert expired.json()["stock_cache_fresh"] is False
    myob.get_main_qty_available.assert_not_called()


def test_stock_refresh_job_reports_progress_and_returns_shared_snapshot(
    tmp_path, monkeypatch
):
    configured = settings(tmp_path)
    items = [stock_item("ITEM1"), stock_item("ITEM2")]
    myob = MagicMock()

    def refresh(item_codes, progress=None):
        assert item_codes == ["ITEM1", "ITEM2"]
        progress(1, 2)
        progress(2, 2)
        return {"ITEM1": 7, "ITEM2": 3}

    myob.get_main_qty_available.side_effect = refresh
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(main, "myob", myob)
    monkeypatch.setattr(
        main, "load_assignment_catalog", lambda refresh=False: (items, 100.0)
    )
    reset_barcode_catalog()
    client = TestClient(main.app)

    started = client.post("/api/stock-on-hand/refresh-jobs")

    assert started.status_code == 202
    job_id = started.json()["job_id"]
    for _ in range(50):
        job = client.get(f"/api/stock-on-hand/refresh-jobs/{job_id}").json()
        if job["status"] == "complete":
            break
        time.sleep(0.01)

    assert job["status"] == "complete"
    assert job["completed"] == 2
    assert job["total"] == 2
    assert [sample["completed"] for sample in job["samples"]] == [0, 1, 2, 2, 2]
    assert job["result"]["quantities"] == {"ITEM1": 7, "ITEM2": 3}
    assert job["result"]["stock_cache_fresh"] is True


def test_barcode_entry_writes_use_the_configured_bounded_concurrency(
    tmp_path, monkeypatch
):
    configured = settings(
        tmp_path,
        barcode_assignment_enabled=True,
        myob_barcode_write_concurrency=2,
    )
    items = [stock_item(f"ITEM{number}") for number in range(6)]
    barcodes = {f"ITEM{number}": f"94000000000{number}" for number in range(6)}
    active = 0
    maximum_active = 0
    counter_lock = threading.Lock()

    def assign_barcode(*_args):
        nonlocal active, maximum_active
        with counter_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.02)
        with counter_lock:
            active -= 1

    def get_items(codes):
        if len(codes) == 6:
            return {item["item_code"]: item for item in items}
        return {
            code: stock_item(
                code,
                barcode=barcodes[code],
                barcode_reference_id=f"xref-{code}",
                barcode_reference_value=barcodes[code],
            )
            for code in codes
        }

    myob = MagicMock()
    myob.assign_barcode.side_effect = assign_barcode
    myob.get_assignment_stock_items.side_effect = get_items
    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(main, "myob", myob)
    monkeypatch.setattr(main, "load_assignment_catalog", lambda: (items, 1.0))
    monkeypatch.setattr(main, "update_stored_assignment_catalog", MagicMock())
    progress = []
    request = BarcodeEntryCommitRequest(
        entries=[
            {"item_code": code, "barcode": barcode}
            for code, barcode in barcodes.items()
        ]
    )

    result = main._commit_entered_barcodes(
        request,
        lambda phase, completed, total, message: progress.append(
            (phase, completed, total, message)
        ),
    )

    assert result["count"] == 6
    assert maximum_active == 2
    assert ("sending", 6, 6, "6/6 sent to MYOB") in progress
    assert ("complete", 6, 6, "6/6 confirmed in MYOB") in progress


def test_barcode_entry_background_job_reports_progress(tmp_path, monkeypatch):
    configured = settings(tmp_path, barcode_assignment_enabled=True)

    def commit(request, progress):
        progress("sending", 1, 2, "1/2 sent to MYOB")
        progress("checking", 2, 2, "Checking 2/2 in MYOB")
        return {
            "entered": [entry.model_dump() for entry in request.entries],
            "removed": [],
            "count": 2,
            "written_count": 2,
            "reassigned_count": 0,
        }

    monkeypatch.setattr(main, "settings", configured)
    monkeypatch.setattr(main, "_commit_entered_barcodes", commit)
    with main.barcode_entry_jobs_lock:
        main.barcode_entry_jobs.clear()
    client = TestClient(main.app)
    response = client.post(
        "/api/barcode-entry/jobs",
        json={
            "entries": [
                {"item_code": "ITEM1", "barcode": "940000000001"},
                {"item_code": "ITEM2", "barcode": "940000000002"},
            ]
        },
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    for _ in range(50):
        job = client.get(f"/api/barcode-entry/jobs/{job_id}").json()
        if job["status"] == "complete":
            break
        time.sleep(0.01)

    assert job["status"] == "complete"
    assert job["phase"] == "complete"
    assert job["completed"] == 2
    assert job["result"]["count"] == 2
