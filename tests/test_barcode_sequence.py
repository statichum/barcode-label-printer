import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.barcode_sequence import BarcodeSequenceError, reserve_barcode_assignments
from app.myob import ean13_internal_barcode, internal_barcode_sequence


def stock_item(item_code: str, sequence: int | None = None) -> dict:
    barcode = ean13_internal_barcode(sequence) if sequence is not None else None
    return {
        "item_code": item_code,
        "description": f"Description for {item_code}",
        "barcode": barcode,
        "barcode_reference_id": None,
        "barcode_reference_value": None,
        "barcode_reference_count": 0,
        "status": "Active",
        "alternate_ids": {barcode} if barcode else set(),
    }


def assignment_sequences(assignments: list[dict]) -> list[int]:
    return [internal_barcode_sequence(item["barcode"]) for item in assignments]


def test_sequence_is_initialized_once_and_abandoned_numbers_are_not_reused(tmp_path):
    active_items = [stock_item("NEW1"), stock_item("NEW2")]
    all_items = [stock_item("INACTIVE", 40), *active_items]
    loads = 0

    def load_all_items():
        nonlocal loads
        loads += 1
        return all_items

    first = reserve_barcode_assignments(
        data_dir=tmp_path,
        item_codes=["NEW1"],
        active_items=active_items,
        load_all_items=load_all_items,
    )
    second = reserve_barcode_assignments(
        data_dir=tmp_path,
        item_codes=["NEW2"],
        active_items=active_items,
        load_all_items=load_all_items,
    )

    assert assignment_sequences(first) == [41]
    assert assignment_sequences(second) == [42]
    assert loads == 1
    state = json.loads((tmp_path / "barcode-sequence.json").read_text())
    assert state["high_water"] == 42


def test_concurrent_previews_reserve_disjoint_blocks(tmp_path):
    active_items = [stock_item(f"NEW{index}") for index in range(4)]

    def reserve(codes):
        return reserve_barcode_assignments(
            data_dir=tmp_path,
            item_codes=codes,
            active_items=active_items,
            load_all_items=lambda: active_items,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(reserve, (["NEW0", "NEW1"], ["NEW2", "NEW3"]))
        )

    sequences = [set(assignment_sequences(result)) for result in results]
    assert sequences[0].isdisjoint(sequences[1])
    assert sequences[0] | sequences[1] == {1, 2, 3, 4}


def test_corrupt_sequence_state_fails_closed(tmp_path):
    (tmp_path / "barcode-sequence.json").write_text("not-json")

    with pytest.raises(BarcodeSequenceError, match="stopped to prevent number reuse"):
        reserve_barcode_assignments(
            data_dir=tmp_path,
            item_codes=["NEW1"],
            active_items=[stock_item("NEW1")],
            load_all_items=lambda: [],
        )


def test_empty_initial_myob_scan_fails_without_creating_counter(tmp_path):
    with pytest.raises(BarcodeSequenceError, match="returned no stock items"):
        reserve_barcode_assignments(
            data_dir=tmp_path,
            item_codes=["NEW1"],
            active_items=[stock_item("NEW1")],
            load_all_items=lambda: [],
        )

    assert not (tmp_path / "barcode-sequence.json").exists()
