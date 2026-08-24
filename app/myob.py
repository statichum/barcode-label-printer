from __future__ import annotations

import threading
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

from .config import Settings
from .database import CatalogItem


class MyobError(RuntimeError):
    pass


class PurchaseOrderNotFound(MyobError):
    pass


def _value(obj: dict, key: str, default=None):
    field = obj.get(key, {})
    return field.get("value", default) if isinstance(field, dict) else default


def _label_quantity(value) -> int:
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return 1
    if quantity <= 0:
        return 1
    return max(1, int(quantity.to_integral_value()))


def merge_purchase_order(order: dict, catalog: dict[str, CatalogItem]) -> dict:
    lines = []
    for detail in order.get("Details", []):
        item_code = str(_value(detail, "InventoryID", "")).strip()
        if not item_code:
            continue
        item = catalog.get(item_code)
        fallback_description = str(
            _value(detail, "LineDescription", item_code) or item_code
        ).strip()
        lines.append(
            {
                "line_number": _value(detail, "LineNbr"),
                "item_code": item_code,
                "description": item.description if item else fallback_description,
                "barcode": item.barcode if item else None,
                "quantity": _label_quantity(_value(detail, "OrderQty", 1)),
                "selected": bool(item and item.barcode),
                "printable": bool(item and item.barcode),
                "warning": None
                if item and item.barcode
                else "No barcode found in the syncer database",
            }
        )
    return {
        "po_number": str(_value(order, "OrderNbr", "")),
        "description": str(_value(order, "Description", "") or ""),
        "date": _value(order, "Date"),
        "lines": lines,
    }


@dataclass
class MyobClient:
    settings: Settings

    def __post_init__(self):
        self._client = httpx.Client(
            base_url=self.settings.myob_base_url,
            verify=self.settings.myob_verify_ssl,
            timeout=self.settings.myob_timeout_seconds,
            follow_redirects=False,
        )
        self._authenticated = False
        self._lock = threading.Lock()

    def _login(self) -> None:
        if not self.settings.myob_username or not self.settings.myob_password:
            raise MyobError("MYOB credentials are not configured")
        response = self._client.post(
            "/entity/auth/login",
            json={
                "name": self.settings.myob_username,
                "password": self.settings.myob_password,
                "company": self.settings.myob_company,
            },
        )
        if response.status_code != 204:
            raise MyobError(f"MYOB login failed with status {response.status_code}")
        self._authenticated = True

    def get_purchase_order(self, po_number: str) -> dict:
        with self._lock:
            if not self._authenticated:
                self._login()
            response = self._request_purchase_order(po_number)
            if response.status_code in {401, 403}:
                self._authenticated = False
                self._login()
                response = self._request_purchase_order(po_number)
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MyobError("MYOB did not return a valid purchase order response") from exc
        if not isinstance(payload, list) or not payload:
            raise PurchaseOrderNotFound(f"Purchase order {po_number} was not found")
        return payload[0]

    def _request_purchase_order(self, po_number: str):
        return self._client.get(
            f"{self.settings.myob_api_root}/PurchaseOrder",
            params={
                "$filter": f"OrderNbr eq '{po_number}'",
                "$expand": "Details",
            },
        )

