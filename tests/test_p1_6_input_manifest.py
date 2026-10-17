from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts.text2sql import run_p1_6_rebaseline as runner


def _canonicalize(record: dict[str, object]):
    canonicalizer = getattr(runner, "canonicalize_input_record", None)
    assert callable(canonicalizer), "P1.6 must expose the shared input-manifest canonicalizer"
    return canonicalizer(record)


def _input_record() -> dict[str, object]:
    return {
        "counts": {"questions": 5},
        "schema_text_sha256": "schema-digest",
        "ordered_node_manifest_sha256": "node-digest",
        "ordered_node_manifest": [
            {"ordinal": 0, "node_id": "db.表", "text_sha256": "text-digest", "token_count": 7}
        ],
    }


def _write_smoke_artifacts(smoke_dir, commit: str) -> dict[str, object]:
    summary = {"run_id": "smoke-5", "mode": "smoke", "status": "smoke_passed", "questions": 5}
    summary_path = smoke_dir / "smoke_summary.json"
    runner.write_json(summary_path, summary)
    receipt = {
        "run_id": "smoke-5",
        "mode": "smoke",
        "status": "smoke_passed",
        "input_manifest_sha256": "a" * 64,
        "question_count": 5,
        "schema_node_count": 3,
        "smoke_summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
    }
    runner.write_json(smoke_dir / "smoke_receipt.json", receipt)
    runner.write_json(
        smoke_dir / "run_start.json",
        {
            "run_id": "smoke-5",
            "mode": "smoke",
            "state": "completed",
            "source": {"published_commit": commit},
        },
    )
    return receipt


def test_saved_smoke_manifest_matches_full_recomputation(tmp_path) -> None:
    record = _input_record()
    smoke_manifest, smoke_nodes, smoke_payload, smoke_digest = _canonicalize(record)
    smoke_path = tmp_path / "input_manifest_private.json"
    smoke_path.write_bytes(smoke_payload)

    full_manifest, full_nodes, full_payload, full_digest = _canonicalize(record)

    expected_payload = (
        '{\n'
        '  "counts": {\n'
        '    "questions": 5\n'
        '  },\n'
        '  "schema_text_sha256": "schema-digest",\n'
        '  "ordered_node_manifest_sha256": "node-digest"\n'
        '}\n'
    ).encode("utf-8")
    assert smoke_manifest == full_manifest
    assert smoke_nodes == full_nodes == record["ordered_node_manifest"]
    assert smoke_payload == full_payload == expected_payload
    assert runner.sha256_file(smoke_path) == smoke_digest == full_digest
    assert "ordered_node_manifest" in record


def test_changing_input_field_changes_private_manifest_hash() -> None:
    original = _input_record()
    changed = deepcopy(original)
    changed["schema_text_sha256"] = "different-schema-digest"

    _, _, _, original_digest = _canonicalize(original)
    _, _, _, changed_digest = _canonicalize(changed)

    assert original_digest != changed_digest


def test_reordering_nodes_changes_ordered_node_manifest_digest() -> None:
    nodes = [
        SimpleNamespace(node_id="db.table.a", db_id="db", node_type="table", text="表 A", token_count=4),
        SimpleNamespace(node_id="db.column.b", db_id="db", node_type="column", text="列 B", token_count=3),
    ]

    _, original_digest = runner.ordered_node_manifest(nodes)
    _, reordered_digest = runner.ordered_node_manifest(list(reversed(nodes)))

    assert original_digest != reordered_digest


def test_full_gate_loads_manifest_hash_from_completed_smoke_receipt(tmp_path) -> None:
    commit = "1" * 40
    expected_receipt = _write_smoke_artifacts(tmp_path, commit)
    loader = getattr(runner, "load_smoke_artifacts", None)
    assert callable(loader), "Full must validate the smoke summary, receipt, and completed run metadata"

    summary, receipt, run_start = loader(tmp_path, commit)

    assert summary["status"] == "smoke_passed"
    assert receipt == expected_receipt
    assert receipt["input_manifest_sha256"] == "a" * 64
    assert run_start["source"]["published_commit"] == commit


def test_full_gate_rejects_smoke_from_a_different_commit(tmp_path) -> None:
    _write_smoke_artifacts(tmp_path, "1" * 40)
    loader = getattr(runner, "load_smoke_artifacts", None)
    assert callable(loader), "Full must validate the smoke summary, receipt, and completed run metadata"

    with pytest.raises(RuntimeError, match="different project commit"):
        loader(tmp_path, "2" * 40)
