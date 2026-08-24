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


def _odata_string(value: str) -> str:
    return value.replace("'", "''")


def _label_quantity(value) -> int:
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return 1
    if quantity <= 0:
        return 1
    return max(1, int(quantity.to_integral_value()))


def stock_item_from_myob(item: dict) -> CatalogItem | None:
    if not isinstance(item, dict):
        return None
    item_code = str(_value(item, "InventoryID", "") or "").strip()
    if not item_code:
        return None
    description = str(_value(item, "Description", item_code) or item_code).strip()
    barcode = next(
        (
            str(_value(reference, "AlternateID", "") or "").strip()
            for reference in (item.get("CrossReferences") or [])
            if _value(reference, "AlternateType") == "Barcode"
        ),
        "",
    )
    if barcode.lower() == "x":
        barcode = ""
    return CatalogItem(
        item_code=item_code,
        description=description,
        barcode=barcode or None,
    )


def merge_catalog_items(
    item_codes: list[str],
    database_items: dict[str, CatalogItem],
    myob_items: dict[str, CatalogItem],
) -> dict[str, CatalogItem]:
    merged: dict[str, CatalogItem] = {}
    for raw_code in item_codes:
        code = raw_code.strip().upper()
        database_item = database_items.get(code)
        myob_item = myob_items.get(code)
        if not database_item and not myob_item:
            continue
        canonical = myob_item.item_code if myob_item else database_item.item_code
        description = (
            database_item.description
            if database_item
            else myob_item.description
        )
        merged[code] = CatalogItem(
            item_code=canonical,
            description=description,
            barcode=myob_item.barcode if myob_item else None,
        )
    return merged


def merge_purchase_order(order: dict, catalog: dict[str, CatalogItem]) -> dict:
    lines = []
    for detail in order.get("Details", []):
        item_code = str(_value(detail, "InventoryID", "")).strip().upper()
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
                else "No barcode cross-reference found in MYOB",
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
        response = self._authenticated_get(
            f"{self.settings.myob_api_root}/PurchaseOrder",
            params={
                "$filter": f"OrderNbr eq '{po_number}'",
                "$expand": "Details",
            },
        )
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MyobError("MYOB did not return a valid purchase order response") from exc
        if not isinstance(payload, list) or not payload:
            raise PurchaseOrderNotFound(f"Purchase order {po_number} was not found")
        return payload[0]

    def get_stock_items(self, item_codes: list[str]) -> dict[str, CatalogItem]:
        codes = list(dict.fromkeys(code.strip().upper() for code in item_codes if code.strip()))
        items: dict[str, CatalogItem] = {}
        for start in range(0, len(codes), 20):
            batch = codes[start : start + 20]
            filters = [
                f"InventoryID eq '{_odata_string(code)}'"
                for code in batch
            ]
            response = self._authenticated_get(
                f"{self.settings.myob_api_root}/StockItem",
                params={
                    "$filter": " or ".join(filters),
                    "$expand": "CrossReferences",
                },
            )
            try:
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise MyobError("MYOB did not return valid stock item data") from exc
            if not isinstance(payload, list):
                raise MyobError("MYOB did not return valid stock item data")
            for raw_item in payload:
                item = stock_item_from_myob(raw_item)
                if item:
                    items[item.item_code.upper()] = item
        return items

    def _authenticated_get(self, path: str, params: dict[str, str]):
        with self._lock:
            if not self._authenticated:
                self._login()
            response = self._client.get(path, params=params)
            if response.status_code in {401, 403}:
                self._authenticated = False
                self._login()
                response = self._client.get(path, params=params)
        return response
