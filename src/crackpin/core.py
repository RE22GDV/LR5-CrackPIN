"""Перебір прообразів хешу. Хешується ASCII-рядок із провідними нулями."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from time import perf_counter


def validate_width(width: int) -> None:
    if type(width) is not int or not 1 <= width <= 12:
        raise ValueError("Довжина PIN має бути цілим числом від 1 до 12")


def validate_hash(target: str, algorithm: str) -> str:
    sizes = {"md5": 32, "sha256": 64, "pbkdf2": 64}
    if algorithm not in sizes:
        raise ValueError("Алгоритм: md5, sha256 або pbkdf2")
    if not isinstance(target, str) or not re.fullmatch(r"[0-9a-fA-F]{%d}" % sizes[algorithm], target):
        raise ValueError(f"Очікується {sizes[algorithm]} шістнадцяткових символів")
    return target.lower()


def digest_pin(pin: str, algorithm: str = "md5", *, salt: bytes = b"", iterations: int = 20_000) -> str:
    """MD5/SHA-256 від salt || PIN; PBKDF2-HMAC-SHA256 із явною сіллю.

    MD5 із префіксом солі — лише навчальна модель, не схема зберігання паролів.
    """
    if not isinstance(pin, str) or not re.fullmatch(r"[0-9]+", pin):
        raise ValueError("PIN має містити лише ASCII-цифри")
    if not isinstance(salt, bytes):
        raise ValueError("Сіль має бути bytes")
    raw = pin.encode("ascii")
    if algorithm == "md5":
        return hashlib.md5(salt + raw).hexdigest()
    if algorithm == "sha256":
        return hashlib.sha256(salt + raw).hexdigest()
    if algorithm == "pbkdf2":
        if type(iterations) is not int or iterations < 1:
            raise ValueError("Кількість ітерацій має бути додатним цілим числом")
        return hashlib.pbkdf2_hmac("sha256", raw, salt, iterations).hex()
    raise ValueError("Невідомий алгоритм")


@dataclass(frozen=True)
class SearchResult:
    pin: str | None
    attempts: int
    seconds: float
    exhausted: bool


def search(target: str, width: int = 5, *, algorithm: str = "md5", salt: bytes = b"",
           iterations: int = 20_000, start: int = 0, stop: int | None = None,
           max_attempts: int | None = None) -> SearchResult:
    """Перебирає [start, stop); exhausted означає вичерпання заданого діапазону.

    Якщо ліміт спрацював раніше, pin=None, exhausted=False: відсутність
    збігу в перевіреній частині не означає відсутності PIN в усьому просторі.
    """
    validate_width(width)
    target = validate_hash(target, algorithm)
    stop = 10**width if stop is None else stop
    if type(start) is not int or type(stop) is not int or not 0 <= start < stop <= 10**width:
        raise ValueError("Потрібен непорожній діапазон 0 <= start < stop <= 10**width")
    if max_attempts is not None and (type(max_attempts) is not int or max_attempts < 1):
        raise ValueError("Ліміт спроб має бути додатним цілим числом")
    # Перевірка алгоритму/солі/ітерацій до запуску циклу.
    digest_pin("0", algorithm, salt=salt, iterations=iterations)
    end = stop if max_attempts is None else min(stop, start + max_attempts)
    begun = perf_counter()
    for attempts, number in enumerate(range(start, end), 1):
        pin = f"{number:0{width}d}"
        if digest_pin(pin, algorithm, salt=salt, iterations=iterations) == target:
            return SearchResult(pin, attempts, perf_counter() - begun, False)
    return SearchResult(None, end - start, perf_counter() - begun, end == stop)


def crack(target: str) -> str | None:
    """Контракт kata: MD5 п'ятизначного PIN -> рядок PIN."""
    return search(target).pin
