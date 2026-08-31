from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

from .config import Settings
from .database import CatalogItem


logger = logging.getLogger("barcode-printer.myob")


class MyobError(RuntimeError):
    pass


class PurchaseOrderNotFound(MyobError):
    pass


class BarcodeAssignmentConflict(MyobError):
    pass


class BarcodeOwnershipConflict(BarcodeAssignmentConflict):
    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        count = len(conflicts)
        super().__init__(
            "1 barcode clashes with another MYOB item"
            if count == 1
            else f"{count} barcodes clash with other MYOB items"
        )


def _value(obj: dict, key: str, default=None):
    field = obj.get(key, {})
    return field.get("value", default) if isinstance(field, dict) else default


def _odata_string(value: str) -> str:
    return value.replace("'", "''")


def _response_error_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    inner = payload.get("innerException")
    if isinstance(inner, dict) and inner.get("exceptionMessage"):
        return str(inner["exceptionMessage"])
    if payload.get("exceptionMessage"):
        return str(payload["exceptionMessage"])
    return None


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
            and str(_value(reference, "AlternateID", "") or "").strip().lower()
            not in {"", "x"}
        ),
        "",
    )
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
    for position, detail in enumerate(order.get("Details", [])):
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
                "po_position": position,
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


def ean13_internal_barcode(sequence: int) -> str:
    if not 1 <= sequence <= 9_999_999_999:
        raise ValueError("Internal barcode sequence is out of range")
    body = f"04{sequence:010d}"
    weighted_sum = sum(
        int(digit) * (3 if position % 2 == 0 else 1)
        for position, digit in enumerate(body, start=1)
    )
    check_digit = (10 - (weighted_sum % 10)) % 10
    return f"{body}{check_digit}"


def internal_barcode_sequence(value: str) -> int | None:
    code = str(value or "").strip()
    if len(code) != 13 or not code.isdigit() or not code.startswith("04"):
        return None
    sequence = int(code[2:12])
    if sequence < 1:
        return None
    return sequence if ean13_internal_barcode(sequence) == code else None


def stock_item_assignment_view(item: dict) -> dict | None:
    catalog_item = stock_item_from_myob(item)
    if not catalog_item:
        return None
    alternate_ids = {
        str(_value(reference, "AlternateID", "") or "").strip()
        for reference in (item.get("CrossReferences") or [])
        if str(_value(reference, "AlternateID", "") or "").strip()
    }
    barcode_references = [
        reference
        for reference in (item.get("CrossReferences") or [])
        if _value(reference, "AlternateType") == "Barcode"
    ]
    barcode_ids = {
        str(_value(reference, "AlternateID", "") or "").strip()
        for reference in barcode_references
        if str(_value(reference, "AlternateID", "") or "").strip()
    }
    barcode_reference = barcode_references[0] if barcode_references else None
    supplier_codes = {
        str(_value(reference, "AlternateID", "") or "").strip()
        for reference in (item.get("CrossReferences") or [])
        if _value(reference, "AlternateType") == "Vendor Part Number"
        and str(_value(reference, "AlternateID", "") or "").strip()
    }
    return {
        "item_code": catalog_item.item_code,
        "description": catalog_item.description,
        "barcode": catalog_item.barcode,
        "barcode_reference_id": barcode_reference.get("id") if barcode_reference else None,
        "barcode_reference_value": (
            str(_value(barcode_reference, "AlternateID", "") or "").strip()
            if barcode_reference
            else None
        ),
        "barcode_reference_count": len(barcode_references),
        "status": str(_value(item, "ItemStatus", "") or "").strip(),
        "alternate_ids": alternate_ids,
        "barcode_ids": barcode_ids,
        "supplier_codes": supplier_codes,
    }


def _barcode_reference_values(item: dict) -> set[str]:
    """Return values stored in Barcode rows, excluding other cross-reference types."""

    if "barcode_ids" in item:
        values = item.get("barcode_ids") or set()
    else:
        # Compatibility with catalogue snapshots written before barcode_ids
        # was stored separately from all other alternate IDs.
        selected = item.get("barcode_reference_value") or item.get("barcode")
        values = {selected} if selected else set()
    return {
        str(value or "").strip()
        for value in values
        if str(value or "").strip()
    }


def supplier_reference_values(item: dict) -> set[str]:
    """Return vendor part numbers, with a fallback for older stored catalogues."""

    if "supplier_codes" in item:
        values = item.get("supplier_codes") or set()
    else:
        values = set(item.get("alternate_ids") or set()) - _barcode_reference_values(item)
    return {
        str(value or "").strip()
        for value in values
        if str(value or "").strip()
    }


def plan_barcode_assignments(
    item_codes: list[str],
    stock_items: list[dict],
    *,
    minimum_sequence: int | None = None,
) -> list[dict]:
    by_code = {item["item_code"].upper(): item for item in stock_items}
    used_ids = {
        barcode
        for item in stock_items
        for barcode in _barcode_reference_values(item)
    }
    missing = [code for code in item_codes if code.upper() not in by_code]
    if missing:
        raise BarcodeAssignmentConflict(
            f"Active stock item not found: {', '.join(missing)}"
        )
    inactive = [
        by_code[code.upper()]["item_code"]
        for code in item_codes
        if by_code[code.upper()].get("status") not in {"", "Active"}
    ]
    if inactive:
        raise BarcodeAssignmentConflict(
            f"Stock item is no longer active: {', '.join(inactive)}"
        )
    duplicate_rows = [
        by_code[code.upper()]["item_code"]
        for code in item_codes
        if by_code[code.upper()].get("barcode_reference_count", 0) > 1
    ]
    if duplicate_rows:
        raise BarcodeAssignmentConflict(
            f"Multiple Barcode rows must be cleaned up in MYOB first: {', '.join(duplicate_rows)}"
        )

    used_sequences = [
        sequence
        for alternate_id in used_ids
        if (sequence := internal_barcode_sequence(alternate_id)) is not None
    ]
    sequence = max(max(used_sequences, default=0) + 1, minimum_sequence or 1)
    assignments = []
    for raw_code in item_codes:
        item = by_code[raw_code.upper()]
        barcode = ean13_internal_barcode(sequence)
        while barcode in used_ids:
            sequence += 1
            barcode = ean13_internal_barcode(sequence)
        assignments.append(
            {
                "item_code": item["item_code"],
                "description": item["description"],
                "barcode": barcode,
                "action": "replace" if item.get("barcode_reference_id") else "create",
                "previous_barcode": item.get("barcode_reference_value"),
                "cross_reference_id": item.get("barcode_reference_id"),
            }
        )
        used_ids.add(barcode)
        sequence += 1
    return assignments


def validate_barcode_assignments(assignments: list[dict], stock_items: list[dict]) -> None:
    by_code = {item["item_code"].upper(): item for item in stock_items}
    used_ids = {
        barcode
        for item in stock_items
        for barcode in _barcode_reference_values(item)
    }
    proposed = set()
    for assignment in assignments:
        item = by_code.get(assignment["item_code"].upper())
        if not item:
            raise BarcodeAssignmentConflict(
                f"{assignment['item_code']} is no longer an active stock item"
            )
        if item.get("barcode_reference_count", 0) > 1:
            raise BarcodeAssignmentConflict(
                f"{item['item_code']} now has multiple Barcode rows"
            )
        if assignment.get("action") == "replace":
            if item.get("barcode_reference_id") != assignment.get("cross_reference_id"):
                raise BarcodeAssignmentConflict(
                    f"The Barcode row for {item['item_code']} changed after preview"
                )
            if item.get("barcode_reference_value") != assignment.get("previous_barcode"):
                raise BarcodeAssignmentConflict(
                    f"The barcode for {item['item_code']} changed after preview"
                )
        elif item.get("barcode_reference_id"):
            raise BarcodeAssignmentConflict(
                f"{item['item_code']} gained a Barcode row after preview"
            )
        barcode = assignment["barcode"]
        if internal_barcode_sequence(barcode) is None:
            raise BarcodeAssignmentConflict(f"{barcode} is not a valid internal barcode")
        if barcode in used_ids or barcode in proposed:
            raise BarcodeAssignmentConflict(f"Barcode {barcode} is already in use")
        proposed.add(barcode)


def refresh_barcode_assignment_targets(
    assignments: list[dict], current_items: dict[str, dict]
) -> list[dict]:
    refreshed = []
    for assignment in assignments:
        code = assignment["item_code"].upper()
        item = current_items.get(code)
        if not item:
            raise BarcodeAssignmentConflict(
                f"{assignment['item_code']} was not found in the final MYOB check"
            )
        if item.get("status") not in {"", "Active"}:
            raise BarcodeAssignmentConflict(
                f"{item['item_code']} is no longer an active stock item"
            )
        if item.get("barcode_reference_count", 0) > 1:
            raise BarcodeAssignmentConflict(
                f"{item['item_code']} now has multiple Barcode rows"
            )

        preview_value = str(assignment.get("previous_barcode") or "").strip()
        current_value = str(item.get("barcode_reference_value") or "").strip()
        preview_missing = not preview_value or preview_value.lower() == "x"
        current_missing = not current_value or current_value.lower() == "x"
        if preview_value != current_value and not (preview_missing and current_missing):
            raise BarcodeAssignmentConflict(
                f"The barcode for {item['item_code']} changed after preview"
            )

        updated = dict(assignment)
        updated["action"] = (
            "replace" if item.get("barcode_reference_id") else "create"
        )
        updated["previous_barcode"] = item.get("barcode_reference_value")
        updated["cross_reference_id"] = item.get("barcode_reference_id")
        refreshed.append(updated)
    return refreshed


def plan_entered_barcodes(
    entries: list[dict],
    current_items: dict[str, dict],
    stock_items: list[dict],
    reassignment_approvals: list[dict] | None = None,
) -> list[dict]:
    used_by_barcode: dict[str, set[str]] = {}
    for item in stock_items:
        item_code = item["item_code"].upper()
        for barcode_value in _barcode_reference_values(item):
            value = str(barcode_value or "").strip()
            if value and value.casefold() != "x":
                used_by_barcode.setdefault(value.casefold(), set()).add(item_code)

    approvals = {
        (
            approval["item_code"].upper(),
            approval["barcode"].strip().casefold(),
            approval["from_item_code"].upper(),
        )
        for approval in (reassignment_approvals or [])
    }
    used_approvals: set[tuple[str, str, str]] = set()
    conflicts: list[dict] = []
    stock_by_code = {item["item_code"].upper(): item for item in stock_items}
    planned: list[dict] = []
    proposed: set[str] = set()
    for entry in entries:
        requested_code = entry["item_code"].upper()
        barcode = entry["barcode"].strip()
        barcode_key = barcode.casefold()
        item = current_items.get(requested_code)
        if not item:
            raise BarcodeAssignmentConflict(
                f"{entry['item_code']} was not found in the final MYOB check"
            )
        if item.get("status") not in {"", "Active"}:
            raise BarcodeAssignmentConflict(
                f"{item['item_code']} is no longer an active stock item"
            )
        if item.get("barcode_reference_count", 0) > 1:
            raise BarcodeAssignmentConflict(
                f"{item['item_code']} has multiple Barcode rows; clean these up in MYOB first"
            )

        current_value = str(item.get("barcode_reference_value") or "").strip()
        current_missing = not current_value or current_value.casefold() == "x"
        current_matches = not current_missing and current_value.casefold() == barcode_key

        owners = used_by_barcode.get(barcode_key, set())
        other_owners = sorted(owner for owner in owners if owner != requested_code)
        if barcode_key in proposed:
            raise BarcodeAssignmentConflict(
                f"Barcode {barcode} appears more than once in this batch"
            )

        transfer_sources = []
        unapproved_owners = []
        for owner_code in other_owners:
            approval_key = (requested_code, barcode_key, owner_code)
            if approval_key not in approvals:
                unapproved_owners.append(owner_code)
                continue
            owner = stock_by_code[owner_code]
            if (
                owner.get("barcode_reference_count") != 1
                or not owner.get("barcode_reference_id")
            ):
                raise BarcodeAssignmentConflict(
                    f"{owner['item_code']} no longer has one removable Barcode row"
                )
            transfer_sources.append(
                {
                    "item_code": owner["item_code"],
                    "barcode": barcode,
                    "cross_reference_id": owner["barcode_reference_id"],
                }
            )
            used_approvals.add(approval_key)
        if unapproved_owners:
            conflicts.append(
                {
                    "barcode": barcode,
                    "item_code": item["item_code"],
                    "owner_item_codes": unapproved_owners,
                }
            )
            continue

        planned.append(
            {
                "item_code": item["item_code"],
                "description": item["description"],
                "barcode": barcode,
                "action": (
                    "unchanged"
                    if current_matches
                    else "replace"
                    if item.get("barcode_reference_id")
                    else "create"
                ),
                "previous_barcode": item.get("barcode_reference_value"),
                "cross_reference_id": item.get("barcode_reference_id"),
                "remove_from": transfer_sources,
            }
        )
        proposed.add(barcode_key)
    if conflicts:
        raise BarcodeOwnershipConflict(conflicts)
    if approvals - used_approvals:
        raise BarcodeAssignmentConflict(
            "Barcode ownership changed after the clash was shown; check the errors and retry"
        )
    return planned


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
        assignment_items = self.get_assignment_stock_items(item_codes)
        return {
            code: CatalogItem(
                item["item_code"],
                item["description"],
                item.get("barcode"),
            )
            for code, item in assignment_items.items()
        }

    def get_assignment_stock_items(self, item_codes: list[str]) -> dict[str, dict]:
        codes = list(dict.fromkeys(code.strip().upper() for code in item_codes if code.strip()))
        items: dict[str, dict] = {}
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
                    "$select": "InventoryID,Description,ItemStatus,CrossReferences",
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
                item = stock_item_assignment_view(raw_item)
                if item:
                    items[item["item_code"].upper()] = item
        return items

    def list_stock_items(self, active_only: bool = True) -> list[dict]:
        page_size = 500
        skip = 0
        items: dict[str, dict] = {}
        while True:
            params = {
                "$top": str(page_size),
                "$skip": str(skip),
                "$select": "InventoryID,Description,ItemStatus,CrossReferences",
                "$expand": "CrossReferences",
                "$orderby": "InventoryID",
            }
            if active_only:
                params["$filter"] = "ItemStatus eq 'Active'"
            response = self._authenticated_get(
                f"{self.settings.myob_api_root}/StockItem",
                params=params,
            )
            try:
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise MyobError("MYOB did not return a valid active stock-item list") from exc
            if not isinstance(payload, list):
                raise MyobError("MYOB did not return a valid active stock-item list")
            previous_count = len(items)
            for raw_item in payload:
                item = stock_item_assignment_view(raw_item)
                if item:
                    items[item["item_code"].upper()] = item
            logger.info(
                "Loaded %s %s stock items from MYOB",
                len(items),
                "active" if active_only else "total",
            )
            if len(payload) < page_size or len(items) == previous_count:
                break
            skip += len(payload)
        return list(items.values())

    def list_active_stock_items(self) -> list[dict]:
        return self.list_stock_items(active_only=True)

    def _get_main_quantity(
        self,
        item_codes: list[str],
        *,
        field_name: str,
        description: str,
    ) -> dict[str, int]:
        selected = {
            code.strip().upper()
            for code in item_codes
            if code and code.strip()
        }
        quantities = {code: 0 for code in selected}
        try:
            availability_timeout = max(self.settings.myob_timeout_seconds, 180)
            response = self._authenticated_request(
                "PUT",
                f"{self.settings.myob_api_root}/WebNinjaInventory",
                params={"$expand": "Result"},
                json={"Result": []},
                timeout=availability_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise MyobError(
                f"MYOB {description} took longer than three minutes; try again"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise MyobError(f"MYOB did not return valid MAIN {description}") from exc
        result = payload.get("Result") if isinstance(payload, dict) else None
        if not isinstance(result, list):
            raise MyobError(f"MYOB did not return valid MAIN {description}")
        for row in result:
            code = str(_value(row, "InventoryID", "") or "").strip().upper()
            warehouse = str(_value(row, "Warehouse", "") or "").strip().upper()
            if code not in selected or warehouse != "MAIN":
                continue
            try:
                quantity = Decimal(str(_value(row, field_name, 0) or 0))
            except (InvalidOperation, TypeError, ValueError):
                continue
            quantities[code] += max(0, int(quantity))
        return quantities

    def get_main_qty_available(self, item_codes: list[str]) -> dict[str, int]:
        return self._get_main_quantity(
            item_codes,
            field_name="QtyAvailable",
            description="stock availability",
        )

    def get_main_qty_on_hand(self, item_codes: list[str]) -> dict[str, int]:
        return self._get_main_quantity(
            item_codes,
            field_name="QtyOnHand",
            description="stock-on-hand data",
        )

    def assign_barcode(
        self,
        item_code: str,
        barcode: str,
        cross_reference_id: str | None = None,
    ) -> None:
        replacement = {
            "AlternateID": {"value": barcode},
            "AlternateType": {"value": "Barcode"},
            "UOM": {"value": "EACH"},
        }
        if cross_reference_id:
            cross_references = [
                {"id": cross_reference_id, "delete": True},
                replacement,
            ]
        else:
            cross_references = [replacement]
        response = self._authenticated_request(
            "PUT",
            f"{self.settings.myob_api_root}/StockItem",
            json={
                "InventoryID": {"value": item_code},
                "CrossReferences": cross_references,
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            detail = _response_error_detail(response)
            suffix = f": {detail}" if detail else ""
            raise MyobError(
                f"MYOB rejected barcode {barcode} for {item_code} "
                f"with HTTP {response.status_code}{suffix}"
            ) from exc

    def remove_barcode(self, item_code: str, cross_reference_id: str) -> None:
        response = self._authenticated_request(
            "PUT",
            f"{self.settings.myob_api_root}/StockItem",
            json={
                "InventoryID": {"value": item_code},
                "CrossReferences": [
                    {"id": cross_reference_id, "delete": True},
                ],
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            detail = _response_error_detail(response)
            suffix = f": {detail}" if detail else ""
            raise MyobError(
                f"MYOB could not remove the conflicting barcode from {item_code} "
                f"with HTTP {response.status_code}{suffix}"
            ) from exc

    def _authenticated_request(self, method: str, path: str, **kwargs):
        with self._lock:
            if not self._authenticated:
                self._login()
            response = self._client.request(method, path, **kwargs)
            if response.status_code in {401, 403}:
                self._authenticated = False
                self._login()
                response = self._client.request(method, path, **kwargs)
        return response

    def _authenticated_get(self, path: str, params: dict[str, str]):
        return self._authenticated_request("GET", path, params=params)
