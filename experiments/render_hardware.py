"""Будує графіки та розділ README з вимірювань; не створює звітів Word/PDF."""

import json
from pathlib import Path

from run_experiments import plt, figure, BLUE, ORANGE, GREEN

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/results"


def number(value, decimals=0):
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")


def main():
    cpu = json.loads((RESULTS / "hardware.json").read_text(encoding="utf-8"))
    gpu = json.loads((RESULTS / "gpu.json").read_text(encoding="utf-8"))
    if cpu["status"] == "running" or gpu["status"] in ("running", "validated", "validating"):
        raise RuntimeError("Спочатку слід завершити вимірювання")
    serial = [r for r in cpu["serial"] if r["complete"]]
    parallel = [r for r in cpu["parallel"] if r["complete"]]
    graphics = [r for r in gpu["cases"] if r["complete"]]
    by_cpu = {(r["alphabet_id"], r["width"]): r for r in serial}
    by_gpu = {(r["alphabet_id"], r["width"]): r for r in graphics}
    colors = [BLUE, GREEN, "#8175b6", "#ad8730", ORANGE, "#bc4662"]
    short_labels = {"digits": "Цифри (10)", "lower": "Малі літери (26)", "upper": "Великі літери (26)",
                    "lower_digits": "Малі + цифри (36)", "mixed": "Два регістри (52)", "mixed_digits": "Два регістри + цифри (62)"}
    fig, ax = plt.subplots(figsize=(9.2, 5))
    for key, color in zip(short_labels, colors):
        rows = [r for r in serial if r["alphabet_id"] == key]
        ax.plot([r["width"] for r in rows], [r["median_seconds"] for r in rows], "o-", color=color, label=short_labels[key])
    ax.set_yscale("log"); ax.set_xlabel("Фіксована довжина пароля, символів")
    ax.set_ylabel("Повний CPU-перебір, с (логарифмічна шкала)")
    ax.legend(fontsize=9, loc="lower right")
    figure(fig, "fig8_real_alphabets.png", "Повністю перебрані простори шести алфавітів на CPU")

    baseline = parallel[0]["median_seconds"]
    workers = [r["workers"] for r in parallel]
    speedups = [baseline/r["median_seconds"] for r in parallel]
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.3))
    axes[0].plot(workers, speedups, "o-", color=BLUE, label="Виміряне прискорення")
    axes[0].plot(workers, workers, "--", color=ORANGE, label="Ідеальне лінійне")
    axes[0].set_ylabel("Прискорення відносно 1 процесу"); axes[0].legend(fontsize=9)
    axes[1].plot(workers, [100*s/w for s, w in zip(speedups, workers)], "o-", color=GREEN)
    axes[1].set_ylabel("Паралельна ефективність, %"); axes[1].set_ylim(0, 110)
    for ax in axes: ax.set_xlabel("Кількість процесів"); ax.set_xticks(workers)
    figure(fig, "fig9_cpu_scaling.png", "Масштабування однакових 14 776 336 перевірок MD5")

    chosen = [("digits", 5), ("digits", 7), ("lower", 5), ("lower", 6),
              ("lower_digits", 5), ("mixed", 5), ("mixed_digits", 5)]
    paired = [key for key in chosen if key in by_cpu and key in by_gpu]
    labels = [f"{short_labels[k].split(' (')[0]} / {d}" for k, d in paired]
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 5.2), sharey=True, gridspec_kw={"width_ratios":[2,1]})
    x = list(range(len(paired)))
    axes[0].barh([i-.19 for i in x], [by_cpu[k]["median_seconds"] for k in paired], .38, color=BLUE, label="CPU, 1 процес")
    axes[0].barh([i+.19 for i in x], [by_gpu[k]["median_wall_seconds"] for k in paired], .38, color=GREEN, label="GPU, весь запуск")
    axes[0].set_xscale("log"); axes[0].set_xlabel("Повний час, с"); axes[0].legend(fontsize=10, loc="lower right")
    axes[0].set_yticks(x, labels, fontsize=11)
    speed = [by_cpu[k]["median_seconds"]/by_gpu[k]["median_wall_seconds"] for k in paired]
    axes[1].barh(x, speed, color=ORANGE); axes[1].set_xlabel("CPU / GPU, разів")
    axes[1].set_xscale("log")
    axes[0].invert_yaxis()
    figure(fig, "fig10_cpu_gpu.png", "CPU та GPU: той самий повністю перевірений простір")

    fig, axes = plt.subplots(1, 2, figsize=(9.4, 4.5))
    ordered = sorted(graphics, key=lambda r: r["space"])
    spaces = [r["space"] for r in ordered]
    axes[0].plot(spaces, [r["median_wall_seconds"] for r in ordered], "o-", color=BLUE, label="Увесь запуск через Python")
    axes[0].plot(spaces, [r["median_kernel_seconds"] for r in ordered], "o-", color=GREEN, label="Сума часу GPU-ядер")
    axes[0].set_yscale("log"); axes[0].set_ylabel("Час, с"); axes[0].legend(fontsize=9)
    axes[1].plot(spaces, [100*(1-r["median_kernel_seconds"]/r["median_wall_seconds"]) for r in ordered], "o-", color=ORANGE)
    axes[1].set_ylabel("Частка часу поза GPU-ядрами, %"); axes[1].set_ylim(0, 100)
    for ax in axes: ax.set_xscale("log"); ax.set_xlabel("Кількість кандидатів (логарифмічна шкала)")
    figure(fig, "fig11_gpu_overhead.png", "Для малих просторів накладні витрати GPU особливо помітні")

    fig, ax = plt.subplots(figsize=(9, 4.7))
    selected = [("digits", 7), ("lower", 6), ("mixed", 5), ("mixed_digits", 5), ("mixed_digits", 6)]
    selected = [k for k in selected if k in by_gpu]
    bars = ax.bar(range(len(selected)), [by_gpu[k]["space"]/by_gpu[k]["median_wall_seconds"]/1e9 for k in selected], color=GREEN)
    ax.set_xticks(range(len(selected)), [f"{short_labels[k].split(' (')[0]}\n{d} символів" for k, d in selected], fontsize=9)
    ax.set_ylabel("Мільярдів перевірок за секунду, весь запуск")
    for b, k in zip(bars, selected):
        value = by_gpu[k]["space"]/by_gpu[k]["median_wall_seconds"]/1e9
        ax.text(b.get_x()+b.get_width()/2, value, number(value, 2), ha="center", va="bottom", fontsize=10)
    ax.set_ylim(0, max(b.get_height() for b in bars)*1.2)
    figure(fig, "fig12_gpu_throughput.png", "Виміряна пропускна здатність GPU для різних просторів")

    lines = ["### 6.6 Реальний апаратний стенд", "",
        "Додатковий експеримент виконував справжнє MD5-хешування синтетичних цифрових і літерних паролів. "
        "Ціль кожного прогону — останній кандидат заданого порядку: це повний найгірший випадок із перевіркою знайденого прообразу.", "",
        "| Компонент | Зафіксована конфігурація |", "|---|---|",
        "| CPU | Intel, 24 ядра, 32 логічні потоки |",
        f"| RAM | {number(cpu['machine']['memory_bytes']/2**30, 2)} ГіБ |",
        f"| GPU | {gpu['device']['name']}, {number(gpu['device']['global_memory_bytes']/2**30, 2)} ГіБ OpenCL-пам’яті |",
        f"| Середовище | Windows 11 Pro; Python 3.12.14; PyOpenCL {gpu['device']['pyopencl_version']} |",
        f"| Драйвер | NVIDIA {gpu['device']['driver_version']}; {gpu['device']['opencl_version']} |", "",
        f"CPU-серія тривала **{number(cpu['elapsed_seconds'], 1)} с**. Зафіксовано {len(serial)} повних послідовних "
        f"конфігурацій та {len(parallel)} конфігурацій паралелізму; сумарно **{number(cpu['total_hash_operations'])}** "
        "MD5-перевірок у вимірюваних прогонах. Частоти не фіксувалися, фон Windows не ізолювався.", "",
        "### 6.7 Короткі паролі: цифри, літери та регістр", "",
        "Досліджено шість алфавітів: `0–9` (10), `a–z` (26), `A–Z` (26), `a–z` + цифри (36), "
        "`a–zA–Z` (52), `a–zA–Z0–9` (62). Довжина фіксована; коротші слова до простору довшого не додаються. "
        "Усі символи — ASCII, одна позиція дорівнює одному байту.", "",
        "![Реальні CPU-прогони шести алфавітів](docs/figures/fig8_real_alphabets.png)", "",
        "| Алфавіт / довжина | Кандидати | CPU, с | Повтори |", "|---|---:|---:|---:|"]
    for key in [("digits", 5), ("digits", 7), ("lower", 5), ("upper", 5), ("lower_digits", 5), ("lower", 6), ("mixed", 5), ("mixed_digits", 5)]:
        if key not in by_cpu: continue
        row = by_cpu[key]
        lines.append(f"| {short_labels[key[0]]}, {key[1]} | {number(row['space'])} | {number(row['median_seconds'], 6)} | {len(row['samples'])} |")
    lines += ["", "Час — медіана повторів. Для найдовших CPU-прогонів виконано один повний повтор через часовий бюджет; "
        "це одиничне спостереження, без оцінки розкиду. Повні короткі прогони мають три повтори. "
        "За однакової довжини розмір простору визначає кількість роботи: для п’яти символів "
        "26 символів дають 11 881 376 кандидатів, 52 — 380 204 032, 62 — 916 132 832. "
        "Зміна регістру без розширення 26-символьного алфавіту не збільшує його потужність.", "",
        "Двійкове порівняння `digest()` у цьому стенді відрізняється від `hexdigest()` у рішенні Codewars. "
        "Тому нові цифрові часи та початкові вимірювання з розділу 6.1 належать різним реалізаціям.", "",
        "### 6.8 Паралельний CPU-перебір", "",
        "Для 1, 2, 4, 8 і 16 процесів виконано той самий простір **62⁴ = 14 776 336** кандидатів. "
        "62 завдання розподіляються за першим символом; кожне перевіряє всі суфікси. "
        "Пул створюється й прогрівається до таймера. Передавання завдань і збирання результатів входять у час.", "",
        "![Прискорення та ефективність CPU](docs/figures/fig9_cpu_scaling.png)", "",
        "| Процеси | Медіана, с | Прискорення | Ефективність |", "|---:|---:|---:|---:|"]
    for r, s in zip(parallel, speedups):
        lines.append(f"| {r['workers']} | {number(r['median_seconds'], 6)} | {number(s, 2)}× | {number(100*s/r['workers'], 1)} % |")
    lines += ["", f"Для 16 процесів прискорення становило **{number(speedups[-1], 2)}×**, "
        f"ефективність — {number(100*speedups[-1]/16, 1)} %. Прискорення визначено як T₁/Tₚ, "
        "ефективність — (T₁/Tₚ)/p. Вони не є лінійними через керування процесами, планувальник, "
        "неоднорідні ядра й інше навантаження. Дослід не вимірює окремо внесок кожної причини.", "",
        "### 6.9 Перебір на GPU та незалежна перевірка", "",
        f"GPU-ядро реалізує 64 кроки одноблокового MD5 за RFC 1321. Перед вимірюваннями "
        f"**{gpu['validation_total']} хешів** для шести алфавітів і довжин 1, 2, 3, 4, 5, 6, 8 "
        "звірено з CPU `hashlib`; усі збіглися. Включено перший і останній кандидати, середину та "
        "псевдовипадкові індекси із зерном 5009. Результати збережено разом з індексами та хешами.", "",
        "Один GPU-потік обробляє один індекс слова: переводить його в систему числення з основою "
        "розміру алфавіту, додає MD5-доповнення, хешує і порівнює всі 128 біт. "
        "Одна група має 256 потоків; пакет — до 33 554 432 кандидатів. "
        "Потоки поза кінцем простору повертаються без хешування. Збіг записується атомарно, "
        "а знайдений рядок повторно перевіряється CPU. Лічильник індексу 64-бітний, тому простір понад 2³² не обрізається.", "",
        "Компіляцію кожного спеціалізованого ядра та окреме прогрівання вилучено з часових показників. "
        "**Час усього запуску** охоплює створення буферів, передавання цілі, запуск пакетів, синхронізацію "
        "та отримання результату. **Час ядер** — сума інтервалів OpenCL `event.profile.end − start`. "
        "Це різні показники, їх наведено окремо. GPU-тести запускалися після CPU-серії.", "",
        "![Порівняння CPU та GPU](docs/figures/fig10_cpu_gpu.png)", "",
        "| Алфавіт / довжина | CPU, с | GPU весь запуск, с | Прискорення |", "|---|---:|---:|---:|"]
    for key, s in zip(paired, speed):
        lines.append(f"| {short_labels[key[0]]}, {key[1]} | {number(by_cpu[key]['median_seconds'], 6)} | {number(by_gpu[key]['median_wall_seconds'], 6)} | {number(s, 1)}× |")
    lines += ["", "Порівняння показує прискорення конкретного стенда: CPU виконує Python-цикл, "
        "GPU — спеціалізоване скомпільоване OpenCL-ядро. Відмінність містить і апаратний паралелізм, "
        "і різні накладні витрати реалізацій; це не чисте порівняння CPU/GPU або мов програмування.", "",
        "### 6.10 GPU: накладні витрати та найбільший простір", "",
        "![Повний час запуску та час GPU-ядер](docs/figures/fig11_gpu_overhead.png)", "",
        "| Алфавіт / довжина | Кандидати | GPU весь запуск, с | GPU ядра, с |", "|---|---:|---:|---:|"]
    for key in selected:
        r = by_gpu[key]
        lines.append(f"| {short_labels[key[0]]}, {key[1]} | {number(r['space'])} | {number(r['median_wall_seconds'], 6)} | {number(r['median_kernel_seconds'], 6)} |")
    largest = max(graphics, key=lambda r:r["space"])
    lines += ["", "![Пропускна здатність GPU](docs/figures/fig12_gpu_throughput.png)", "",
        f"Найбільший повністю перевірений GPU-простір — **{number(largest['space'])}** "
        f"кандидатів ({largest['alphabet_size']} символів, довжина {largest['width']}). "
        f"Медіана повного запуску — **{number(largest['median_wall_seconds'], 6)} с**, "
        f"пропускна здатність — **{number(largest['space']/largest['median_wall_seconds']/1e9, 2)} млрд/с**. "
        "Це результат реального повного перебору, а не екстраполяція. "
        "На малому просторі створення буферів і запуск займають помітну частку часу; на великому "
        "домінує обчислення. Зростання довжини не гарантує сталої GPU-швидкості: змінюються "
        "перетворення індексів та код спеціалізованого ядра.", "",
        f"GPU-серія містить {len(graphics)} повних конфігурацій та "
        f"**{number(gpu['measured_hash_operations'])}** MD5-перевірок у вимірюваних повторах. "
        "Прогрівання до цієї кількості не включено. Сирі дані: `hardware.json`, `gpu.json`; "
        "протокол: `docs/hardware_methodology.md`. Часткові прогони, якщо вони є, "
        "залишаються в JSON із `complete: false` та не включаються до цих таблиць.", ""]
    rate = largest["space"]/largest["median_wall_seconds"]
    lines += ["### 6.11 Розрахункова межа для довших паролів", "",
        f"Для ілюстрації використано виміряну швидкість найбільшого GPU-простору "
        f"{number(rate/1e9, 2)} млрд/с. За умовної незмінної швидкості повний час "
        "62-символьного алфавіту дорівнює 62ᵈ/r, середній за рівномірного вибору — (62ᵈ+1)/(2r). "
        "Наведені далі простори **не перебиралися**. Це екстраполяція, яка не враховує "
        "зміну GPU-коду, частот, накладних витрат і довжини. Реалізація стенда підтримує лише довжини до 8; "
        "значення для 9–10 символів є суто математичним продовженням моделі.", "",
        "| Довжина | Кандидати | Оцінка повного часу, год |", "|---:|---:|---:|"]
    for d in range(7, 11):
        lines.append(f"| {d} | {number(62**d)} | {number(62**d/rate/3600, 3)} |")
    lines += ["", "Так видно, що межа практичності зміщується разом із ресурсом атаки. "
        "Шість випадкових буквено-цифрових символів уже створюють десятки мільярдів варіантів, "
        "але цей простір ще доступний сучасному GPU для швидкого MD5. "
        "Цей висновок стосується локального відомого хешу й цього стенда, а не будь-якого сервісу "
        "або повільної функції зберігання паролів.", ""]
    section = "\n".join(lines)
    (RESULTS / "hardware_summary.md").write_text("# Реальні CPU/GPU-вимірювання\n\n"+section, encoding="utf-8")
    readme = ROOT / "README.md"
    content = readme.read_text(encoding="utf-8")
    if "### 6.6 Реальний апаратний стенд" in content:
        start = content.index("### 6.6 Реальний апаратний стенд")
        end = content.index("## 7.", start)
        content = content[:start]+section+"\n---\n\n"+content[end:]
    else:
        content = content.replace("## 7. Криптоаналіз", section+"\n---\n\n## 7. Криптоаналіз")
    content = content.replace("# Повний набір тестів і сім графіків", "# Повний набір тестів і початкові сім графіків")
    reproduction = """```bash
# Апаратні CPU-досліди: не більше 25 хвилин
# У Windows спочатку оновити метадані обладнання
powershell -File experiments/collect_machine.ps1
python experiments/hardware_benchmark.py --max-seconds 1500

# GPU потребує драйвера з OpenCL; необов’язкові залежності
python -m pip install -r requirements-gpu.txt
python experiments/gpu_benchmark.py --validate-only
python experiments/gpu_benchmark.py
python experiments/render_hardware.py
```

GPU-серія без явного аргументу має бюджет 600 секунд. Для спільного обмеження CPU/GPU
можна задати GPU `--wait-for-cpu --deadline-utc` з абсолютним UTC-часом завершення.
Перед запуском CPU метадані обладнання можна зберегти у `docs/results/machine.json`;
GPU-скрипт сам зчитує дані пристрою. CPU-програма читає наявний файл метаданих,
а версію Python, платформу та кількість логічних CPU визначає при кожному запуску.
Графіки будуються після завершення вимірювань.

"""
    if "# Апаратні CPU-досліди" not in content:
        content = content.replace("Векторні PDF графіків", reproduction+"Векторні PDF графіків")
    if "7. Khronos" not in content:
        content = content.replace("\n---\n\n<p align=\"center\"><sub>", "\n7. Khronos. [OpenCL API: profiling events](https://registry.khronos.org/OpenCL/specs/3.0-unified/html/OpenCL_API.html).\n8. PyOpenCL. [Command queues and events](https://documen.tician.de/pyopencl/runtime_queue.html).\n\n---\n\n<p align=\"center\"><sub>")
    readme.write_text(content, encoding="utf-8")
    print(json.dumps({"cpu_cases":len(serial), "gpu_cases":len(graphics), "largest_gpu_space":largest["space"], "new_figures":5}))


if __name__ == "__main__":
    main()
