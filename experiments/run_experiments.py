"""Вимірювання, первинні дані та рисунки. Не генерує звітів Word/PDF.

Часові оцінки залежать від машини. Seed фіксує входи, а не час виконання.
"""

from __future__ import annotations

import hashlib
import json
import platform
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from crackpin import build_table, digest_pin, search, time_estimate
from crackpin.analysis import synthetic_guessing_model

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SURFACE, INK, GRID = "#fcfcfb", "#0b0b0b", "#e3e2de"
BLUE, ORANGE, GREEN = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "axes.edgecolor": GRID, "axes.labelcolor": INK,
    "axes.titlecolor": INK, "axes.titlesize": 12, "axes.titleweight": "semibold",
    "axes.labelsize": 10, "axes.grid": True, "axes.axisbelow": True,
    "grid.color": GRID, "legend.frameon": False, "font.family": "DejaVu Sans"})
FIG = ROOT / "docs/figures"
OUT = ROOT / "docs/results"
REPEATS = 3


def stats(values):
    return {"samples_seconds": values, "median_seconds": statistics.median(values),
            "min_seconds": min(values), "max_seconds": max(values)}


def python_scan(width, count):
    """Той самий прямий цикл, що у solution/codewars_solution.py."""
    target = hashlib.md5(b"outside-PIN-domain").hexdigest()
    begun = perf_counter()
    for number in range(count):
        pin = f"{number:0{width}d}"
        if hashlib.md5(pin.encode("ascii")).hexdigest() == target:
            raise AssertionError("Несподіваний збіг із контрольним хешем")
    return perf_counter() - begun


def figure(fig, name, title):
    # Версія без заголовка для вставляння у звіт із зовнішнім підписом.
    fig.tight_layout()
    fig.savefig(FIG / "pdf" / name, dpi=200)
    fig.savefig(FIG / "pdf" / name.replace(".png", ".pdf"))
    fig.suptitle(title, fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, .94])
    fig.savefig(FIG / name, dpi=180)
    plt.close(fig)


def run():
    for p in (FIG, FIG / "pdf", OUT):
        p.mkdir(parents=True, exist_ok=True)
    rng = random.Random(5005)
    results = {"protocol_version": 1, "seed": 5005, "repeats": REPEATS,
        "environment": {"python": sys.version, "platform": platform.platform(),
            "machine": platform.machine(), "processor": platform.processor(),
            "measured_at_utc": datetime.now(timezone.utc).isoformat(),
            "timer": "time.perf_counter", "parallel_workers": 1},
        "notes": ["Локальний CPU, без GPU; час не є універсальною характеристикою мови.",
            "1–6 цифр виміряно повністю. 7–12 цифр — екстраполяція.",
            "PBKDF2 20 000 ітерацій — навчальний параметр, не рекомендація.",
            "MD5 з префіксом солі — навчальна модель, не password KDF."]}

    python_scan(5, 1000)
    rows = []
    for width in range(1, 7):
        count = 10**width
        row = {"width": width, "count": count, "measured": True,
               "python": stats([python_scan(width, count) for _ in range(REPEATS)])}
        rows.append(row)
    results["lengths"] = rows
    rate = rows[4]["count"] / rows[4]["python"]["median_seconds"]
    results["baseline_rate_per_second"] = rate
    results["extrapolations"] = [{"width": d, "measured": False, **time_estimate(d, rate)} for d in range(7, 13)]

    position_pins = [0, 1, 123, 1234, 12345, 50000, 90000, 99999]
    results["positions"] = [{"pin": f"{n:05d}", "attempts": n+1,
        **stats([search(digest_pin(f"{n:05d}")).seconds for _ in range(REPEATS)])} for n in position_pins]

    hash_rows = []
    for algorithm, count in [("md5", 50_000), ("sha256", 50_000), ("pbkdf2", 200)]:
        samples = []
        last = None
        for _ in range(REPEATS):
            begun = perf_counter()
            for i in range(count):
                last = digest_pin(f"{i:05d}", algorithm, salt=b"account-A", iterations=20_000)
            samples.append(perf_counter() - begun)
        row = {"algorithm": algorithm, "count_per_repeat": count, "iterations": 20_000 if algorithm == "pbkdf2" else None,
               "last_digest": last, **stats(samples)}
        row["rate_per_second"] = count / row["median_seconds"]
        row["estimated_worst_5_digit_seconds"] = 100_000 / row["rate_per_second"]
        hash_rows.append(row)
    results["hash_costs"] = hash_rows

    begun = perf_counter()
    table = build_table()
    build_seconds = perf_counter() - begun
    memory = sys.getsizeof(table) + sum(sys.getsizeof(k) + sys.getsizeof(v) for k, v in table.items())
    pins = [f"{rng.randrange(100_000):05d}" for _ in range(2000)]
    targets = [digest_pin(p) for p in pins]
    lookups = []
    for _ in range(REPEATS):
        begun = perf_counter()
        recovered = [table[h] for h in targets]
        lookups.append(perf_counter() - begun)
        assert recovered == pins
    query_pins = [f"{rng.randrange(100_000):05d}" for _ in range(20)]
    query_times = [search(digest_pin(p)).seconds for p in query_pins]
    mean_query = statistics.mean(query_times)
    lookup_per_query = statistics.median(lookups) / len(pins)
    results["precomputation"] = {"entries": len(table), "collisions": 100_000 - len(table),
        "build_seconds": build_seconds, "accounted_object_bytes": memory,
        "memory_method": "sys.getsizeof(dict) + сума розмірів ключів і значень; не RSS процесу",
        "lookup_count_per_repeat": len(pins), "lookup_samples_seconds": lookups,
        "lookup_seconds_per_query": lookup_per_query, "query_pins": query_pins,
        "bruteforce_query_seconds": query_times, "mean_bruteforce_query_seconds": mean_query,
        "amortization_queries": build_seconds / (mean_query - lookup_per_query)}

    account_pins = [f"{1000*i:04d}" for i in range(10)]
    account_targets = {digest_pin(p) for p in account_pins}
    found = set()
    begun = perf_counter()
    for i in range(10_000):
        h = digest_pin(f"{i:04d}")
        if h in account_targets:
            found.add(h)
        if found == account_targets:
            break
    shared = {"attempts": i + 1, "seconds": perf_counter() - begun, "found": len(found)}
    salted = []
    for i, pin in enumerate(account_pins):
        salt = f"account-{i}".encode()
        salted.append(search(digest_pin(pin, salt=salt), 4, salt=salt))
    assert [r.pin for r in salted] == account_pins
    misses = sum(digest_pin(p, salt=f"account-{i}".encode()) not in table for i, p in enumerate(account_pins))
    results["salt"] = {"width": 4, "accounts": 10, "pins": account_pins,
        "unsalted_shared_scan": shared, "salted_attempts": sum(r.attempts for r in salted),
        "salted_seconds": sum(r.seconds for r in salted), "unsalted_table_misses": misses,
        "worst_hash_operations": {"shared_unsalted": 10_000, "unique_salts": 100_000}}

    flips = [(int(digest_pin(f"{i:05d}"), 16) ^ int(digest_pin(f"{i+1:05d}"), 16)).bit_count() for i in range(1000)]
    results["diffusion"] = {"pairs": len(flips), "mean_changed_bits": statistics.mean(flips),
                            "min_changed_bits": min(flips), "max_changed_bits": max(flips), "counts": flips}
    results["budgets"] = [{"alphabet": a, "label": label, "width": d,
                           **time_estimate(d, rate, a)} for a, label in [(10,"Цифри"),(26,"Латинські малі"),(62,"Літери й цифри")] for d in range(4,13)]
    results["guessing_model"] = synthetic_guessing_model()
    (OUT/"experiments.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plot(results)
    summary(results)
    print(json.dumps({"rate": rate, "five_digit_seconds": rows[4]["python"]["median_seconds"],
        "six_digit_seconds": rows[5]["python"]["median_seconds"], "table_MiB": memory/2**20,
        "amortization_queries": results["precomputation"]["amortization_queries"]}, indent=2))


def plot(r):
    fig, ax = plt.subplots(figsize=(8.8,4.6))
    rows = r["lengths"]
    x = [v["width"] for v in rows]
    ax.plot(x, [v["python"]["median_seconds"] for v in rows], "o-", color=BLUE, label="Python — виміряно")
    ax.plot([6]+[v["width"] for v in r["extrapolations"]], [rows[5]["python"]["median_seconds"]]+[v["worst_seconds"] for v in r["extrapolations"]], "o--", color=ORANGE, label="Python — оцінка за швидкістю 5 цифр")
    ax.set_yscale("log"); ax.set_xlabel("Кількість цифр"); ax.set_ylabel("Повний перебір, с (логарифмічна шкала)"); ax.legend()
    figure(fig,"fig1_length.png","Кожна додаткова цифра збільшує простір у 10 разів")

    fig, axes = plt.subplots(1,2,figsize=(9,4.3))
    p = r["positions"]
    axes[0].plot([int(v["pin"]) for v in p],[v["attempts"] for v in p], "o-",color=BLUE)
    axes[0].set_xlabel("Числове значення PIN"); axes[0].set_ylabel("Спроби до збігу")
    axes[1].plot([v["attempts"] for v in p],[v["median_seconds"]*1000 for v in p],"o-",color=ORANGE)
    axes[1].set_xlabel("Спроби до збігу"); axes[1].set_ylabel("Час бібліотечного пошуку, мс")
    figure(fig,"fig2_position.png","Однакова довжина PIN не означає однаковий час пошуку")

    fig, ax = plt.subplots(figsize=(8.5,4.3))
    rows = r["hash_costs"]
    values = [v["rate_per_second"] for v in rows]
    bars=ax.bar(["MD5", "SHA-256", "PBKDF2 SHA-256\n20 000 ітерацій"],values,color=[BLUE,GREEN,ORANGE])
    ax.set_yscale("log"); ax.set_ylabel("Кандидатів за секунду (логарифмічна шкала)")
    for b,v in zip(bars,values): ax.text(b.get_x()+b.get_width()/2,v*1.12,f"{v:,.0f}".replace(","," "),ha="center",fontsize=10)
    ax.set_ylim(min(values)/2,max(values)*3)
    figure(fig,"fig3_hash_cost.png","Вартість перевірки кандидата впливає на час атаки")

    fig, ax = plt.subplots(figsize=(8.5,4.3))
    p=r["precomputation"]; x=list(range(1,21))
    ax.plot(x,[n*p["mean_bruteforce_query_seconds"] for n in x],"o-",color=BLUE,label="Окремий перебір для кожного PIN")
    ax.plot(x,[p["build_seconds"]+n*p["lookup_seconds_per_query"] for n in x],"s-",color=ORANGE,label="Одна повна таблиця + пошук")
    ax.set_xlabel("Кількість запитів"); ax.set_ylabel("Оцінка сумарного часу, с"); ax.legend()
    figure(fig,"fig4_precomputation.png","Попередня таблиця переносить витрати на етап підготовки")

    fig, axes = plt.subplots(1,2,figsize=(9,4.3))
    s=r["salt"]
    axes[0].bar(["Спільний перебір\nбез солі","Окремі перебори\nз відомими солями"],[s["unsalted_shared_scan"]["attempts"],s["salted_attempts"]],color=[BLUE,ORANGE])
    axes[0].set_ylabel("Виміряна кількість хешувань")
    axes[1].hist(r["diffusion"]["counts"],bins=range(40,91,3),color=GREEN,edgecolor=SURFACE)
    axes[1].axvline(64,color=ORANGE,linestyle="--",label="64 біти")
    axes[1].set_xlabel("Змінені біти MD5 із 128"); axes[1].set_ylabel("Кількість пар"); axes[1].legend()
    figure(fig,"fig5_salt_diffusion.png","Вплив солі на перебір та дифузія MD5")

    fig, ax = plt.subplots(figsize=(8.8,4.6))
    for a,color,label in [(10,BLUE,"Цифри — 10 символів"),(26,GREEN,"Малі літери — 26 символів"),(62,ORANGE,"Літери й цифри — 62 символи")]:
        rows=[v for v in r["budgets"] if v["alphabet"]==a]
        ax.plot([v["width"] for v in rows],[v["mean_seconds"] for v in rows],"o-",color=color,label=label)
    for seconds,label in [(60,"1 хв"),(3600,"1 год"),(86400,"1 доба")]:
        ax.axhline(seconds,color="#8b8983",linestyle="--",linewidth=.8); ax.text(12.05,seconds,label,va="center",fontsize=9)
    ax.set_yscale("log"); ax.set_xlabel("Довжина рівномірно обраного пароля"); ax.set_ylabel("Оцінка середнього часу, с"); ax.legend(loc="upper left")
    figure(fig,"fig6_budget.png","Межа практичності залежить від алфавіту та бюджету атаки")

    fig, ax = plt.subplots(figsize=(8.8,4.4))
    rows=r["guessing_model"]["curves"]
    for key,color,label in [("uniform_success",GREEN,"Рівномірний PIN"),("numeric_success",BLUE,"Синтетичний PIN — числовий порядок"),("priority_success",ORANGE,"Синтетичний PIN — найімовірніші спочатку")]:
        ax.plot([v["budget"] for v in rows],[100*v[key] for v in rows],"o-",color=color,label=label)
    ax.set_xscale("log"); ax.set_xlabel("Бюджет перевірок (логарифмічна шкала)"); ax.set_ylabel("Імовірність успіху, %"); ax.legend()
    figure(fig,"fig7_distribution.png","Однакова довжина допускає різну ймовірність вгадування")


def summary(r):
    lines=["# Первинні результати експериментів", "", "Медіана трьох прогонів; один CPU-потік. Фіксоване зерно 5005.","",
        "| Цифри | Спроби | Python, с |", "|---|---:|---:|"]
    for row in r["lengths"]:
        lines.append(f"| {row['width']} | {row['count']} | {row['python']['median_seconds']:.6f} |")
    lines += ["", "## Оцінки для довших PIN", "", "Ці простори не перебиралися; використано швидкість прямого Python-циклу на 5 цифрах.", "", "| Цифри | Повний перебір, с | Середній час, с |", "|---|---:|---:|"]
    for row in r["extrapolations"]: lines.append(f"| {row['width']} | {row['worst_seconds']:.3f} | {row['mean_seconds']:.3f} |")
    lines += ["", "Сирі тривалості, метадані, параметри та обмеження: [experiments.json](experiments.json).",
              "", "Таблиця прообразів перевірена на всіх 100 000 PIN. Сіль не збільшує простір одного PIN.",
              "PBKDF2-параметр є навчальним. Час не є прогнозом продуктивності GPU або іншого комп'ютера."]
    (OUT/"summary.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


if __name__ == "__main__":
    run()
