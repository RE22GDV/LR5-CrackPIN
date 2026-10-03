import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run([sys.executable, str(ROOT/"run.py"), *args], capture_output=True, text=True, encoding="utf-8", timeout=30)


def test_json_leading_zeros():
    result = run("crack", hashlib.md5(b"00007").hexdigest(), "--json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["pin"] == "00007" and data["attempts"] == 8


def test_cli_limit_is_not_success():
    result = run("crack", hashlib.md5(b"99999").hexdigest(), "--max-attempts", "10", "--json")
    assert result.returncode == 1
    assert json.loads(result.stdout)["exhausted"] is False


def test_cli_invalid_hash():
    result = run("crack", "invalid")
    assert result.returncode == 2


def test_cli_hash_preserves_zeros():
    result = run("hash", "00001")
    assert result.returncode == 0 and result.stdout.strip() == hashlib.md5(b"00001").hexdigest()


def test_cli_explicit_rate():
    result = run("keyspace", "--length", "5", "--rate", "1000")
    assert json.loads(result.stdout)["mean_seconds"] == 50.0005
