"""Перевіряє цілісність первинних даних без повторення тривалих дослідів."""

import hashlib
import json
from pathlib import Path
import statistics

import pytest

from crackpin.gpu import ordinal_word

DATA = Path(__file__).resolve().parents[1] / "docs/results"


@pytest.fixture
def cpu():
    return json.loads((DATA / "hardware.json").read_text(encoding="utf-8"))


@pytest.fixture
def gpu():
    return json.loads((DATA / "gpu.json").read_text(encoding="utf-8"))


def test_cpu_complete_spaces_and_preimages(cpu):
    assert cpu["status"] in ("completed", "time_limit_reached")
    for row in cpu["serial"]:
        assert row["space"] == row["alphabet_size"]**row["width"]
        assert row["median_seconds"] == statistics.median(s["seconds"] for s in row["samples"])
        for sample in row["samples"]:
            if not sample["complete"]: continue
            assert sample["attempts"] == row["space"]
            assert sample["recovered"] == row["alphabet"][-1]*row["width"]
            assert hashlib.md5(sample["recovered"].encode("ascii")).hexdigest() == sample["target_md5"]


def test_cpu_parallel_and_total_operation_counts(cpu):
    for row in cpu["parallel"]:
        assert row["space"] == 62**4
        assert row["median_seconds"] == statistics.median(s["seconds"] for s in row["samples"])
        for s in row["samples"]:
            if s["complete"]: assert s["attempts"] == row["space"]
    actual = sum(s["attempts"] for r in cpu["serial"]+cpu["parallel"] for s in r["samples"])
    assert actual == cpu["total_hash_operations"]


def test_gpu_reference_hashes(gpu, cpu):
    alphabets = {r["alphabet_id"]:r["alphabet"] for r in cpu["serial"]}
    assert len(gpu["validation"]) == 42
    assert gpu["validation_total"] == sum(r["passed"] for r in gpu["validation"])
    for row in gpu["validation"]:
        alphabet = alphabets[row["alphabet_id"]]
        expected = [hashlib.md5(ordinal_word(i, alphabet, row["width"]).encode("ascii")).hexdigest() for i in row["indices"]]
        assert row["hashes"] == expected
        assert row["passed"] == len(expected)


def test_gpu_complete_counts_preimages_and_timers(gpu):
    assert gpu["status"] in ("completed", "time_limit_reached")
    for row in gpu["cases"]:
        assert row["space"] == row["alphabet_size"]**row["width"]
        assert row["median_wall_seconds"] == statistics.median(s["wall_seconds"] for s in row["samples"])
        assert row["median_kernel_seconds"] == statistics.median(s["kernel_seconds"] for s in row["samples"])
        for s in row["samples"]:
            assert s["wall_seconds"] >= s["kernel_seconds"] > 0
            assert s["kernel_seconds"] == pytest.approx(sum(s["kernel_batch_seconds"]))
            assert s["batch_count"] == len(s["kernel_batch_seconds"])
            if not s["complete"]: continue
            assert s["attempts"] == row["space"] and s["recovered"] == s["expected"]
            assert hashlib.md5(s["recovered"].encode("ascii")).hexdigest() == s["target_md5"]
    assert gpu["measured_hash_operations"] == sum(s["attempts"] for r in gpu["cases"] for s in r["samples"])
