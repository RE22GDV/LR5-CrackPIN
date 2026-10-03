"""Аналітичні оцінки і повна таблиця прообразів (не rainbow table)."""

from __future__ import annotations

import math

from .core import digest_pin, validate_width


def keyspace(width: int, alphabet_size: int = 10) -> dict:
    if type(width) is not int or width < 1 or type(alphabet_size) is not int or alphabet_size < 2:
        raise ValueError("Довжина >= 1, розмір алфавіту >= 2")
    count = alphabet_size**width
    return {"count": count, "entropy_bits": math.log2(count), "mean_attempts": (count + 1) / 2}


def time_estimate(width: int, rate: float, alphabet_size: int = 10) -> dict:
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("Швидкість має бути додатною і скінченною")
    space = keyspace(width, alphabet_size)
    return {**space, "worst_seconds": space["count"] / rate, "mean_seconds": space["mean_attempts"] / rate}


def build_table(width: int = 5, *, salt: bytes = b"") -> dict[str, str]:
    """Усі MD5; відмова при колізії не дозволяє мовчки втратити кандидата."""
    validate_width(width)
    if width > 6:
        raise ValueError("Навчальна таблиця обмежена 10**6 елементами")
    table = {}
    for number in range(10**width):
        pin = f"{number:0{width}d}"
        digest = digest_pin(pin, salt=salt)
        if digest in table:
            raise RuntimeError(f"Колізія: {table[digest]} та {pin}")
        table[digest] = pin
    return table


def synthetic_guessing_model() -> dict:
    """Контрольована модель: P(00000)=0.2, P(12345)=0.1, решта рівномірні.

    Не є статистикою людського вибору PIN. Числовий порядок порівнюється
    з порядком спадання заданих імовірностей без зміни самого простору.
    """
    count = 100_000
    residual = .7 / (count - 2)
    mean_numeric = .2 + .1*12346 + residual*(count*(count+1)/2 - 1 - 12346)
    mean_priority = .2 + .1*2 + .7*(count+3)/2
    entropy = -.2*math.log2(.2) - .1*math.log2(.1) - .7*math.log2(residual)
    curves = []
    for budget in (1, 2, 10, 100, 1000, 10_000, 12345, 12346, 50_000, 100_000):
        special = int(budget >= 1) + int(budget >= 12346)
        numeric = (.2 if budget >= 1 else 0) + (.1 if budget >= 12346 else 0) + residual*(budget-special)
        priority = .2 if budget == 1 else .3 + residual*(budget-2)
        curves.append({"budget": budget, "uniform_success": budget/count,
                       "numeric_success": numeric, "priority_success": priority})
    return {"description": "Синтетична модель, не спостереження за користувачами",
        "p_00000": .2, "p_12345": .1, "p_each_other": residual,
        "entropy_bits": entropy, "mean_numeric_attempts": mean_numeric,
        "mean_priority_attempts": mean_priority, "curves": curves}
