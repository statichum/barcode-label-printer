from unittest.mock import MagicMock

from app import main
from app.database import CatalogItem
from app.models import PrintRequest


def _print_result(model: str) -> dict:
    return {
        "job_id": "test-job",
        "status": "dry-run",
        "label_count": 1,
        "printer": {"model": model},
        "delivery": None,
    }


def test_large_print_request_uses_zebra_service(monkeypatch):
    item = CatalogItem("ITEM-1", "Example item", "9412345678901")
    standard = MagicMock()
    large = MagicMock()
    large.print_items.return_value = _print_result("ZD421")
    monkeypatch.setattr(main, "printing", standard)
    monkeypatch.setattr(main, "large_printing", large)
    monkeypatch.setattr(main, "load_catalog_items", lambda codes: {"ITEM-1": item})

    result = main.print_labels(
        PrintRequest(
            items=[{"item_code": "ITEM-1", "quantity": 1}],
            label_size="large",
        )
    )

    assert result["printer"]["model"] == "ZD421"
    large.print_items.assert_called_once()
    standard.print_items.assert_not_called()


def test_large_printer_status_is_selected_explicitly(monkeypatch):
    standard = MagicMock()
    large = MagicMock()
    large.status.return_value = {"online": True, "model": "ZD421"}
    monkeypatch.setattr(main, "discovery", standard)
    monkeypatch.setattr(main, "large_discovery", large)

    assert main.printer_status("large") == {"online": True, "model": "ZD421"}
    large.status.assert_called_once()
    standard.status.assert_not_called()
