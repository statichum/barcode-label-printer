from __future__ import annotations

import fcntl
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .myob import (
    _barcode_reference_values,
    internal_barcode_sequence,
    plan_barcode_assignments,
)


logger = logging.getLogger("barcode-printer.sequence")
_process_lock = threading.Lock()


class BarcodeSequenceError(RuntimeError):
    pass


def _highest_sequence(items: list[dict]) -> int:
    sequences = (
        internal_barcode_sequence(barcode)
        for item in items
        for barcode in _barcode_reference_values(item)
    )
    return max((sequence for sequence in sequences if sequence is not None), default=0)


def _state_error(message: str, exc: Exception | None = None) -> BarcodeSequenceError:
    error = BarcodeSequenceError(
        f"The persistent barcode sequence file is {message}; barcode assignment "
        "has been stopped to prevent number reuse"
    )
    if exc is not None:
        error.__cause__ = exc
    return error


def _read_state(path: Path) -> tuple[int, float] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise _state_error("unreadable", exc)
    try:
        version = payload["version"]
        high_water = int(payload["high_water"])
        initialized_at = float(payload["initialized_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise _state_error("invalid", exc)
    if (
        version != 1
        or not 0 <= high_water <= 9_999_999_999
        or initialized_at <= 0
    ):
        raise _state_error("invalid")
    return high_water, initialized_at


def _write_state(path: Path, high_water: int, *, initialized_at: float) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "version": 1,
                "high_water": high_water,
                "initialized_at": initialized_at,
                "updated_at": time.time(),
            },
            handle,
        )
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def reserve_barcode_assignments(
    *,
    data_dir: Path,
    item_codes: list[str],
    active_items: list[dict],
    load_all_items: Callable[[], list[dict]],
) -> list[dict]:
    """Atomically reserve monotonically increasing barcode numbers.

    Missing state is initialized once from active and inactive MYOB items. A
    reserved number is persisted before the preview is returned and is never
    released, even if that preview is abandoned.
    """

    data_dir.mkdir(parents=True, exist_ok=True)
    state_path = data_dir / "barcode-sequence.json"
    lock_path = data_dir / "barcode-sequence.lock"
    with _process_lock, lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            state = _read_state(state_path)
            if state is None:
                initialized_at = time.time()
                logger.info(
                    "Initializing the barcode sequence from all MYOB stock items"
                )
                all_items = load_all_items()
                if not all_items:
                    raise BarcodeSequenceError(
                        "MYOB returned no stock items during barcode sequence "
                        "initialization; barcode assignment has been stopped to "
                        "prevent number reuse"
                    )
                high_water = _highest_sequence(all_items)
                _write_state(
                    state_path,
                    high_water,
                    initialized_at=initialized_at,
                )
                logger.info(
                    "Initialized the persistent barcode sequence at %s", high_water
                )
            else:
                high_water, initialized_at = state

            assignments = plan_barcode_assignments(
                item_codes,
                active_items,
                minimum_sequence=high_water + 1,
            )
            reserved_sequences = [
                internal_barcode_sequence(item["barcode"]) or 0
                for item in assignments
            ]
            reserved_low_water = min(reserved_sequences)
            reserved_high_water = max(reserved_sequences)
            _write_state(
                state_path,
                reserved_high_water,
                initialized_at=initialized_at,
            )
            logger.info(
                "Reserved barcode sequences %s through %s for %s item(s)",
                reserved_low_water,
                reserved_high_water,
                len(assignments),
            )
            return assignments
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
