"""Командний інтерфейс лабораторної роботи."""

import argparse
import json
from pathlib import Path

from .core import digest_pin, search
from .analysis import time_estimate


def main(argv=None):
    parser = argparse.ArgumentParser(description="ЛР5 — Crack the PIN")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("crack", help="Відновити PIN за MD5")
    p.add_argument("hash")
    p.add_argument("--length", type=int, default=5)
    p.add_argument("--max-attempts", type=int, default=1_000_000)
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p = commands.add_parser("hash", help="MD5 цифрового PIN")
    p.add_argument("pin")
    p = commands.add_parser("keyspace", help="Оцінка за заданою швидкістю")
    p.add_argument("--length", type=int, default=5)
    p.add_argument("--rate", type=float, default=1_000_000)
    p.add_argument("--alphabet", type=int, default=10)
    commands.add_parser("selftest", help="Локальні контрольні приклади")
    args = parser.parse_args(argv)
    try:
        if args.command == "hash":
            print(digest_pin(args.pin))
        elif args.command == "keyspace":
            print(json.dumps(time_estimate(args.length, args.rate, args.alphabet), indent=2))
        elif args.command == "selftest":
            root = Path(__file__).resolve().parents[2]
            cases = json.loads((root / "tests" / "reference_cases.json").read_text(encoding="utf-8"))["cases"]
            for case in cases:
                result = search(case["hash"])
                assert result.pin == case["pin"], case
                print(f"[OK] {case['pin']} — {result.attempts} спроб")
            print(f"Пройдено {len(cases)} з {len(cases)}")
        else:
            from dataclasses import asdict
            result = search(args.hash, args.length, start=args.start, max_attempts=args.max_attempts)
            if args.json:
                print(json.dumps(asdict(result)))
            elif result.pin is not None:
                print(f"PIN: {result.pin}\nСпроб: {result.attempts}\nЧас: {result.seconds:.6f} с")
            else:
                print("PIN не знайдено" if result.exhausted else "Досягнуто ліміту; пошук не завершено")
            return 0 if result.pin is not None else 1
    except ValueError as error:
        parser.error(str(error))
    return 0
