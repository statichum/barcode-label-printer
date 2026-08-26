from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
import time
from pathlib import Path

import psycopg
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .barcode_sequence import BarcodeSequenceError, reserve_barcode_assignments
from .config import Settings
from .database import CatalogRepository
from .labels import PrintService
from .models import (
    BarcodeAdminLoginRequest,
    BarcodeAssignmentCommitRequest,
    BarcodeAssignmentPreviewRequest,
    ManualItemLookupRequest,
    PrintRequest,
    PurchaseOrderLookupRequest,
    StaffLabelPrintRequest,
)
from .myob import (
    BarcodeAssignmentConflict,
    MyobClient,
    MyobError,
    PurchaseOrderNotFound,
    merge_catalog_items,
    merge_purchase_order,
    refresh_barcode_assignment_targets,
    validate_barcode_assignments,
)
from .printer import PrinterDiscovery, PrinterUnavailable


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("barcode-printer")

settings = Settings.from_env()
catalog = CatalogRepository(settings)
myob = MyobClient(settings)
discovery = PrinterDiscovery(settings)
printing = PrintService(settings, discovery)

app = FastAPI(
    title="PRV Barcode Printer",
    version="1.5.0",
    docs_url="/api/docs",
    redoc_url=None,
)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

barcode_admin_sessions: dict[str, float] = {}
barcode_assignment_previews: dict[str, dict] = {}
barcode_catalog_cache: dict = {"items": None, "stored_at": None, "generation": 0}
barcode_admin_lock = threading.Lock()
barcode_catalog_refresh_lock = threading.Lock()


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Barcode administration PIN required")
    return authorization.removeprefix("Bearer ").strip()


def require_barcode_admin(authorization: str | None) -> str:
    token = _bearer_token(authorization)
    now = time.monotonic()
    with barcode_admin_lock:
        expires_at = barcode_admin_sessions.get(token, 0)
        if expires_at <= now:
            barcode_admin_sessions.pop(token, None)
            raise HTTPException(status_code=401, detail="Barcode administration session expired")
    return token


def _barcode_catalog_path() -> Path:
    return settings.data_dir / "barcode-stock-items.json"


def _read_stored_assignment_catalog() -> tuple[list[dict], float] | None:
    path = _barcode_catalog_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload["items"]
        stored_at = float(payload["stored_at"])
        if payload.get("version") != 2 or not isinstance(items, list):
            raise ValueError("unsupported catalogue format")
        return items, stored_at
    except FileNotFoundError:
        return None
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring unreadable stored barcode catalogue: %s", exc)
        return None


def _write_stored_assignment_catalog(items: list[dict], stored_at: float) -> None:
    path = _barcode_catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"version": 2, "stored_at": stored_at, "items": items}),
        encoding="utf-8",
    )
    temporary.replace(path)


def _set_assignment_catalog(items: list[dict], stored_at: float) -> None:
    with barcode_admin_lock:
        barcode_catalog_cache["items"] = items
        barcode_catalog_cache["stored_at"] = stored_at
        barcode_catalog_cache["generation"] += 1


def _stored_assignment_item(item: dict) -> dict:
    stored = dict(item)
    stored["alternate_ids"] = sorted(item.get("alternate_ids", []))
    return stored


def _public_assignment_catalog(items: list[dict]) -> list[dict]:
    return [
        {
            "item_code": item["item_code"],
            "description": item["description"],
            "barcode": item.get("barcode_reference_value"),
            "assignable": item.get("barcode_reference_count", 0) <= 1,
            "warning": (
                "Multiple Barcode rows must be cleaned up in MYOB"
                if item.get("barcode_reference_count", 0) > 1
                else None
            ),
        }
        for item in items
        if item.get("status") == "Active"
    ]


def load_assignment_catalog(refresh: bool = False) -> tuple[list[dict], float]:
    with barcode_admin_lock:
        starting_generation = barcode_catalog_cache["generation"]

    # Only one request may walk the large MYOB catalogue at a time. Requests
    # that arrived while that walk was running reuse its result.
    with barcode_catalog_refresh_lock:
        with barcode_admin_lock:
            cached_items = barcode_catalog_cache["items"]
            stored_at = barcode_catalog_cache["stored_at"]
            refreshed_while_waiting = (
                barcode_catalog_cache["generation"] != starting_generation
            )
            if cached_items is not None and (not refresh or refreshed_while_waiting):
                return cached_items, stored_at

        if not refresh:
            stored = _read_stored_assignment_catalog()
            if stored is not None:
                items, stored_at = stored
                active_items = [item for item in items if item.get("status") == "Active"]
                if len(active_items) != len(items):
                    _write_stored_assignment_catalog(active_items, stored_at)
                items = active_items
                _set_assignment_catalog(items, stored_at)
                logger.info("Loaded %s stock items from the stored catalogue", len(items))
                return items, stored_at

        items = [
            _stored_assignment_item(item)
            for item in myob.list_active_stock_items()
        ]
        stored_at = time.time()
        _write_stored_assignment_catalog(items, stored_at)
        _set_assignment_catalog(items, stored_at)
        logger.info("Stored %s refreshed stock items", len(items))
        return items, stored_at


def update_stored_assignment_catalog(verified_items: dict[str, dict]) -> None:
    with barcode_catalog_refresh_lock:
        with barcode_admin_lock:
            items = barcode_catalog_cache["items"]
            stored_at = barcode_catalog_cache["stored_at"]
        if items is None:
            stored = _read_stored_assignment_catalog()
            if stored is None:
                return
            items, stored_at = stored
        updated_items = []
        for item in items:
            verified = verified_items.get(item["item_code"].upper())
            updated_items.append(
                _stored_assignment_item(verified) if verified else item
            )
        _write_stored_assignment_catalog(updated_items, stored_at)
        _set_assignment_catalog(updated_items, stored_at)


def load_catalog_items(item_codes: list[str]):
    codes = list(dict.fromkeys(code.strip().upper() for code in item_codes if code.strip()))
    database_items = catalog.get_items(codes)
    myob_items = myob.get_stock_items(codes)
    return merge_catalog_items(codes, database_items, myob_items)


@app.on_event("startup")
def startup() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.spool_dir.mkdir(parents=True, exist_ok=True)
    missing = settings.validate_runtime()
    if missing:
        logger.warning("Missing runtime settings: %s", ", ".join(missing))


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(static_dir / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "PRV Barcode Printer",
        "print_enabled": settings.print_enabled,
        "barcode_assignment_enabled": settings.barcode_assignment_enabled,
        "missing_configuration": settings.validate_runtime(),
    }


@app.post("/api/barcode-admin/login")
def barcode_admin_login(request: BarcodeAdminLoginRequest):
    if not settings.barcode_admin_pin:
        raise HTTPException(status_code=503, detail="BARCODE_ADMIN_PIN is not configured")
    if not hmac.compare_digest(request.pin, settings.barcode_admin_pin):
        raise HTTPException(status_code=401, detail="Incorrect barcode administration PIN")
    token = secrets.token_urlsafe(32)
    expires_in = max(5, settings.barcode_admin_session_minutes) * 60
    with barcode_admin_lock:
        barcode_admin_sessions[token] = time.monotonic() + expires_in
    return {"token": token, "expires_in_seconds": expires_in}


@app.get("/api/barcode-admin/items")
def barcode_admin_items(
    refresh: bool = False,
    authorization: str | None = Header(default=None),
):
    require_barcode_admin(authorization)
    try:
        items, stored_at = load_assignment_catalog(refresh=refresh)
    except MyobError as exc:
        logger.warning("MYOB barcode catalog lookup failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"items": _public_assignment_catalog(items), "stored_at": stored_at}


@app.post("/api/barcode-admin/assignments/preview")
def preview_barcode_assignments(
    request: BarcodeAssignmentPreviewRequest,
    authorization: str | None = Header(default=None),
):
    admin_token = require_barcode_admin(authorization)
    try:
        all_items, _ = load_assignment_catalog()
        assignments = reserve_barcode_assignments(
            data_dir=settings.data_dir,
            item_codes=request.item_codes,
            active_items=all_items,
            load_all_items=lambda: myob.list_stock_items(active_only=False),
        )
    except BarcodeAssignmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BarcodeSequenceError as exc:
        logger.error("Barcode sequence reservation failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MyobError as exc:
        logger.warning("Barcode catalogue lookup failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    preview_token = secrets.token_urlsafe(32)
    with barcode_admin_lock:
        barcode_assignment_previews[preview_token] = {
            "admin_token": admin_token,
            "assignments": assignments,
            "expires_at": time.monotonic() + 600,
        }
    return {
        "preview_token": preview_token,
        "assignments": assignments,
        "writes_enabled": settings.barcode_assignment_enabled,
    }


@app.post("/api/barcode-admin/assignments/commit")
def commit_barcode_assignments(
    request: BarcodeAssignmentCommitRequest,
    authorization: str | None = Header(default=None),
):
    admin_token = require_barcode_admin(authorization)
    if not settings.barcode_assignment_enabled:
        raise HTTPException(
            status_code=503,
            detail="Barcode writes are disabled; set BARCODE_ASSIGNMENT_ENABLED=true to enable them",
        )
    with barcode_admin_lock:
        preview = barcode_assignment_previews.pop(request.preview_token, None)
    if (
        not preview
        or preview["admin_token"] != admin_token
        or preview["expires_at"] <= time.monotonic()
    ):
        raise HTTPException(status_code=409, detail="Assignment preview expired; review the items again")

    assignments = preview["assignments"]
    try:
        all_items, _ = load_assignment_catalog()
        current_items = myob.get_assignment_stock_items(
            [item["item_code"] for item in assignments]
        )
        assignments = refresh_barcode_assignment_targets(assignments, current_items)
        validation_items = [
            current_items.get(item["item_code"].upper(), item)
            for item in all_items
        ]
        validate_barcode_assignments(assignments, validation_items)
    except BarcodeAssignmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MyobError as exc:
        logger.warning("Final barcode catalogue check failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    assigned = []
    try:
        for assignment in assignments:
            myob.assign_barcode(
                assignment["item_code"],
                assignment["barcode"],
                assignment.get("cross_reference_id"),
            )
            assigned.append(assignment)
        verified = myob.get_assignment_stock_items(
            [item["item_code"] for item in assignments]
        )
        failed_verification = [
            item["item_code"]
            for item in assignments
            if verified.get(item["item_code"].upper()) is None
            or verified[item["item_code"].upper()].get("barcode") != item["barcode"]
        ]
        if failed_verification:
            raise MyobError(
                f"MYOB did not return the assigned barcode for: {', '.join(failed_verification)}"
            )
    except MyobError as exc:
        logger.exception("Barcode assignment failed after %s successful writes", len(assigned))
        suffix = (
            f" {len(assigned)} item(s) were already updated; refresh before retrying."
            if assigned
            else ""
        )
        raise HTTPException(status_code=502, detail=f"{exc}.{suffix}".strip()) from exc

    update_stored_assignment_catalog(verified)
    logger.info("Assigned MYOB barcodes to %s item(s)", len(assigned))
    return {"assigned": assigned, "count": len(assigned)}


@app.post("/api/barcode-admin/stock-labels")
def barcode_assignment_stock_labels(
    request: BarcodeAssignmentPreviewRequest,
    authorization: str | None = Header(default=None),
):
    require_barcode_admin(authorization)
    catalogue, _ = load_assignment_catalog()
    by_code = {item["item_code"].upper(): item for item in catalogue}
    try:
        quantities = myob.get_main_qty_available(request.item_codes)
    except MyobError as exc:
        logger.warning("MYOB MAIN stock availability lookup failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    items = []
    zero_stock = []
    limited = []
    for code in request.item_codes:
        item = by_code.get(code.upper())
        if not item:
            continue
        available = max(0, quantities.get(code.upper(), 0))
        if available <= 0:
            zero_stock.append(item["item_code"])
            continue
        quantity = min(available, 999)
        if available > 999:
            limited.append(item["item_code"])
        items.append(
            {
                "item_code": item["item_code"],
                "description": item["description"],
                "barcode": item.get("barcode"),
                "quantity": quantity,
                "qty_available": available,
                "selected": bool(item.get("barcode")),
                "printable": bool(item.get("barcode")),
                "warning": (
                    f"MAIN QtyAvailable is {available}; label quantity is limited to 999"
                    if available > 999
                    else None
                ),
            }
        )
    return {
        "warehouse": "MAIN",
        "items": items,
        "zero_stock": zero_stock,
        "limited": limited,
    }


@app.get("/api/printer/status")
def printer_status():
    return discovery.status()


@app.post("/api/purchase-orders/lookup")
def purchase_order_lookup(request: PurchaseOrderLookupRequest):
    try:
        order = myob.get_purchase_order(request.po_number)
        item_codes = [
            str(line.get("InventoryID", {}).get("value", "")).strip()
            for line in order.get("Details", [])
        ]
        enriched = load_catalog_items(item_codes)
        return merge_purchase_order(order, enriched)
    except PurchaseOrderNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MyobError as exc:
        logger.warning("MYOB lookup failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except psycopg.Error as exc:
        logger.exception("Database lookup failed")
        raise HTTPException(
            status_code=503,
            detail="The syncer database is currently unavailable",
        ) from exc


@app.post("/api/items/lookup")
def manual_item_lookup(request: ManualItemLookupRequest):
    try:
        found = load_catalog_items(request.item_codes)
    except MyobError as exc:
        logger.warning("MYOB stock item lookup failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except psycopg.Error as exc:
        logger.exception("Database lookup failed")
        raise HTTPException(
            status_code=503,
            detail="The syncer database is currently unavailable",
        ) from exc
    return {
        "items": [
            {
                "item_code": found[code].item_code if code in found else code,
                "description": found[code].description if code in found else code,
                "barcode": found[code].barcode if code in found else None,
                "quantity": 1,
                "selected": bool(code in found and found[code].barcode),
                "printable": bool(code in found and found[code].barcode),
                "warning": None
                if code in found and found[code].barcode
                else "Item or barcode cross-reference not found in MYOB",
            }
            for code in request.item_codes
        ]
    }


@app.post("/api/print")
def print_labels(request: PrintRequest):
    requested_codes = [item.item_code for item in request.items]
    try:
        found = load_catalog_items(requested_codes)
    except MyobError as exc:
        logger.warning("MYOB stock item lookup failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except psycopg.Error as exc:
        logger.exception("Database lookup failed")
        raise HTTPException(
            status_code=503,
            detail="The syncer database is currently unavailable",
        ) from exc

    missing = [
        code for code in dict.fromkeys(requested_codes) if code not in found or not found[code].barcode
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"No printable barcode found for: {', '.join(missing)}",
        )

    try:
        result = printing.print_items(
            [(found[item.item_code], item.quantity) for item in request.items],
            source=request.source,
            reference=request.reference,
        )
    except ValueError as exc:
        logger.warning("Label generation failed: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PrinterUnavailable as exc:
        logger.warning("Printer connection failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    logger.info(
        "Print job %s %s with %s labels",
        result["job_id"],
        result["status"],
        result["label_count"],
    )
    return result


@app.post("/api/staff-labels/print")
def print_staff_label(request: StaffLabelPrintRequest):
    try:
        result = printing.print_staff_label(
            name=request.name,
            badge_code=request.badge_code,
            quantity=request.quantity,
        )
    except ValueError as exc:
        logger.warning("Staff label generation failed: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PrinterUnavailable as exc:
        logger.warning("Staff label printer connection failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    logger.info(
        "Staff label job %s %s for %s",
        result["job_id"],
        result["status"],
        request.name,
    )
    return result
