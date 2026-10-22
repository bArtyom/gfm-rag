import hashlib
import json

import pytest

from scripts.text2sql import p2d_v2_saved_replay as replay


def test_prediction_payload_and_seal_file_are_validated_with_separate_hashes(tmp_path, monkeypatch):
    predictions_path = tmp_path / "predictions_private.json"
    seal_path = tmp_path / "prediction_seal.json"
    payload = b"[]\n"
    payload_sha = hashlib.sha256(payload).hexdigest()
    seal = {
        "predictions_sha256": payload_sha,
        "prepare_seal_sha256": "prepared-input-seal",
    }
    seal_bytes = (json.dumps(seal, sort_keys=True) + "\n").encode("utf-8")
    seal_sha = hashlib.sha256(seal_bytes).hexdigest()
    predictions_path.write_bytes(payload)
    seal_path.write_bytes(seal_bytes)

    monkeypatch.setattr(replay, "EXPECTED_PREDICTIONS_SHA256", payload_sha)
    monkeypatch.setattr(replay, "EXPECTED_PREDICTION_SEAL_SHA256", seal_sha)
    monkeypatch.setattr(replay, "EXPECTED_PREPARE_SEAL_SHA256", "prepared-input-seal")

    predictions, loaded_seal = replay.load_prediction_bundle(tmp_path)

    assert predictions == []
    assert loaded_seal == seal

    seal_path.write_bytes(seal_bytes + b" ")
    with pytest.raises(RuntimeError, match="prediction seal file hash mismatch"):
        replay.load_prediction_bundle(tmp_path)
