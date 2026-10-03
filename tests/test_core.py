import hashlib
import importlib.util
import json
import random
from pathlib import Path

import pytest

from crackpin import build_table, crack, digest_pin, keyspace, search, time_estimate

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("pin", ["00000", "00001", "00123", "01234", "12345", "54321", "99999"])
def test_reference_and_standalone(pin):
    cases = json.loads((ROOT / "tests/reference_cases.json").read_text(encoding="utf-8"))["cases"]
    target = next(c["hash"] for c in cases if c["pin"] == pin)
    spec = importlib.util.spec_from_file_location("kata_solution", ROOT / "solution/codewars_solution.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert crack(target) == pin
    assert module.crack(target) == pin
    assert search(target).attempts == int(pin) + 1


@pytest.mark.parametrize("text,expected", [
    ("1", "c4ca4238a0b923820dcc509a6f75849b"),
    ("12345", "827ccb0eea8a706c4c34a16891f84e7b"),
    ("00000", "dcddb75469b4b4875094e14561e573d8"),
])
def test_known_md5(text, expected):
    assert digest_pin(text) == expected


def test_leading_zeros_are_part_of_message():
    assert digest_pin("1") != digest_pin("00001")
    assert len(crack(digest_pin("00001"))) == 5


def test_uppercase_hash():
    assert crack(digest_pin("00123").upper()) == "00123"


def test_missing_preimage():
    result = search(hashlib.md5(b"100000").hexdigest())
    assert result.pin is None and result.attempts == 100_000 and result.exhausted


def test_limit_does_not_claim_exhaustion():
    result = search(digest_pin("00009"), max_attempts=9)
    assert result.pin is None and result.attempts == 9 and not result.exhausted
    assert search(digest_pin("00009"), max_attempts=10).pin == "00009"


def test_resume_and_half_open_range():
    target = digest_pin("00123")
    assert search(target, start=100, stop=124).attempts == 24
    result = search(target, start=100, stop=123)
    assert result.pin is None and result.exhausted


def test_limit_covering_range_is_exhaustion():
    result = search(digest_pin("00099"), start=0, stop=10, max_attempts=10)
    assert result.exhausted and result.attempts == 10


@pytest.mark.parametrize("target", ["", "f"*31, "f"*33, "g"*32, " " + "f"*31, "\n" + "f"*31, None, 123])
def test_invalid_hash(target):
    with pytest.raises(ValueError):
        search(target)


@pytest.mark.parametrize("width", [0, -1, 13, 1.5, True, "5"])
def test_invalid_width(width):
    with pytest.raises(ValueError):
        search("f"*32, width)


@pytest.mark.parametrize("pin", ["", "１２３４５", "١٢٣٤٥", "1234a", "-1234", "12 34", 12345])
def test_only_ascii_digits(pin):
    with pytest.raises(ValueError):
        digest_pin(pin)


@pytest.mark.parametrize("limits", [{"start": -1}, {"start": 100_000}, {"stop": 100_001},
    {"stop": 0}, {"start": 20, "stop": 10}, {"max_attempts": 0}, {"max_attempts": -1},
    {"max_attempts": True}, {"start": True}])
def test_invalid_bounds(limits):
    with pytest.raises(ValueError):
        search("f"*32, **limits)


@pytest.mark.parametrize("algorithm", ["md5", "sha256", "pbkdf2"])
def test_salted_search(algorithm):
    salt = b"account-A"
    pin = "007"
    expected = digest_pin(pin, algorithm, salt=salt, iterations=10)
    assert search(expected, 3, algorithm=algorithm, salt=salt, iterations=10).pin == pin
    assert search(expected, 3, algorithm=algorithm, salt=b"account-B", iterations=10).pin is None


def test_pbkdf2_against_standard_library():
    assert digest_pin("123", "pbkdf2", salt=b"test", iterations=2) == hashlib.pbkdf2_hmac("sha256", b"123", b"test", 2).hex()


@pytest.mark.parametrize("options", [{"algorithm": "sha1"}, {"salt": "string"}, {"algorithm": "pbkdf2", "iterations": 0}, {"algorithm": "pbkdf2", "iterations": True}])
def test_invalid_hashing_options(options):
    with pytest.raises(ValueError):
        digest_pin("12345", **options)


@pytest.mark.parametrize("width", [1, 2, 3])
def test_random_round_trip(width):
    rng = random.Random(500 + width)
    for _ in range(25):
        pin = f"{rng.randrange(10**width):0{width}d}"
        assert search(hashlib.md5(pin.encode()).hexdigest(), width).pin == pin


def test_complete_five_digit_domain_and_no_collisions():
    table = build_table()
    assert len(table) == 100_000
    # Інший генератор кандидатів і стандартна hashlib, без digest_pin.
    from itertools import product
    for digits in product("0123456789", repeat=5):
        pin = "".join(digits)
        assert table[hashlib.md5(pin.encode()).hexdigest()] == pin


def test_salt_invalidates_reusable_table():
    table = build_table(2)
    for pin in ("00", "01", "42", "99"):
        assert digest_pin(pin, salt=b"unique") not in table
    assert build_table(2, salt=b"unique")[digest_pin("42", salt=b"unique")] == "42"


def test_table_memory_guard():
    with pytest.raises(ValueError):
        build_table(7)


def test_keyspace_and_exact_mean():
    space = keyspace(5)
    assert space["count"] == 100_000
    assert space["mean_attempts"] == 50_000.5
    assert space["entropy_bits"] == pytest.approx(16.609640474)
    assert time_estimate(5, 1000)["worst_seconds"] == 100
    assert time_estimate(5, 1000)["mean_seconds"] == 50.0005


@pytest.mark.parametrize("rate", [0, -1, float("nan"), float("inf")])
def test_invalid_rates(rate):
    with pytest.raises(ValueError):
        time_estimate(5, rate)


@pytest.mark.parametrize("width,alphabet", [(0,10), (5,1), (True,10), (5,True)])
def test_invalid_keyspaces(width, alphabet):
    with pytest.raises(ValueError):
        keyspace(width, alphabet)


def test_synthetic_prior_is_normalized_and_prioritization_helps():
    from crackpin.analysis import synthetic_guessing_model
    row = synthetic_guessing_model()
    assert row["p_00000"] + row["p_12345"] + 99_998*row["p_each_other"] == pytest.approx(1)
    assert row["mean_priority_attempts"] < row["mean_numeric_attempts"] < 50_000.5
    assert row["curves"][1]["priority_success"] == pytest.approx(.3)
    assert row["curves"][-1]["priority_success"] == pytest.approx(1)
