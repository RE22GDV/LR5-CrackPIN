"""Аудит збережених результатів: обчислені твердження мають збігатися з сирими даними."""

import json
import statistics
from pathlib import Path

import pytest

FILE = Path(__file__).resolve().parents[1] / "docs/results/experiments.json"


@pytest.fixture
def results():
    return json.loads(FILE.read_text(encoding="utf-8"))


def test_recorded_timings_and_medians(results):
    assert [row["width"] for row in results["lengths"]] == list(range(1, 7))
    for row in results["lengths"]:
        assert row["count"] == 10**row["width"] and row["measured"] is True
        for language in ("python",):
            values = row[language]["samples_seconds"]
            assert len(values) == results["repeats"] and all(t > 0 for t in values)
            assert row[language]["median_seconds"] == statistics.median(values)


def test_estimates_follow_recorded_rate(results):
    rate = results["baseline_rate_per_second"]
    assert rate == 100_000 / results["lengths"][4]["python"]["median_seconds"]
    for row in results["extrapolations"]:
        assert row["measured"] is False
        assert row["worst_seconds"] == pytest.approx(10**row["width"] / rate)
        assert row["mean_seconds"] == pytest.approx((10**row["width"] + 1) / (2*rate))


def test_precomputation_amortization(results):
    row = results["precomputation"]
    expected = row["build_seconds"] / (statistics.mean(row["bruteforce_query_seconds"]) - row["lookup_seconds_per_query"])
    assert row["amortization_queries"] == pytest.approx(expected)
    assert row["entries"] == 100_000 and row["collisions"] == 0


def test_salt_work_matches_actual_pins(results):
    row = results["salt"]
    assert row["salted_attempts"] == sum(int(pin)+1 for pin in row["pins"])
    assert row["unsalted_shared_scan"]["attempts"] == max(map(int,row["pins"]))+1
    assert row["unsalted_shared_scan"]["found"] == row["accounts"]


def test_hashing_rates_and_diffusion(results):
    for row in results["hash_costs"]:
        assert row["rate_per_second"] == pytest.approx(row["count_per_repeat"]/statistics.median(row["samples_seconds"]))
    row = results["diffusion"]
    assert row["pairs"] == len(row["counts"])
    assert row["mean_changed_bits"] == statistics.mean(row["counts"])
