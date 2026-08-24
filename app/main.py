from __future__ import annotations

import logging
from pathlib import Path

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .database import CatalogRepository
from .labels import PrintService
from .models import ManualItemLookupRequest, PrintRequest, PurchaseOrderLookupRequest
from .myob import MyobClient, MyobError, PurchaseOrderNotFound, merge_purchase_order
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
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


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
        "missing_configuration": settings.validate_runtime(),
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
        enriched = catalog.get_items(code for code in item_codes if code)
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
        found = catalog.get_items(request.item_codes)
    except psycopg.Error as exc:
        logger.exception("Database lookup failed")
        raise HTTPException(
            status_code=503,
            detail="The syncer database is currently unavailable",
        ) from exc
    return {
        "items": [
            {
                "item_code": code,
                "description": found[code].description if code in found else code,
                "barcode": found[code].barcode if code in found else None,
                "quantity": 1,
                "selected": bool(code in found and found[code].barcode),
                "printable": bool(code in found and found[code].barcode),
                "warning": None
                if code in found and found[code].barcode
                else "Item or barcode not found in the syncer database",
            }
            for code in request.item_codes
        ]
    }


@app.post("/api/print")
def print_labels(request: PrintRequest):
    requested_codes = [item.item_code for item in request.items]
    try:
        found = catalog.get_items(requested_codes)
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
    except (PrinterUnavailable, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    logger.info(
        "Print job %s %s with %s labels",
        result["job_id"],
        result["status"],
        result["label_count"],
    )
    return result
