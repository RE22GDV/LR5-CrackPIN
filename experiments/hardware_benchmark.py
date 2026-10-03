"""Реальні CPU-перебори цифрових і буквено-цифрових паролів.

Приклади синтетичні. Жодних звернень до сервісів чи чужих хешів немає.
Ліміт часу охоплює всі послідовні й паралельні експерименти разом.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import statistics
import string
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs/results/hardware.json"
ALPHABETS={
    "digits":("Цифри",string.digits),
    "lower":("Малі латинські літери",string.ascii_lowercase),
    "upper":("Великі латинські літери",string.ascii_uppercase),
    "lower_digits":("Малі літери й цифри",string.ascii_lowercase+string.digits),
    "mixed":("Латинські літери двох регістрів",string.ascii_letters),
    "mixed_digits":("Два регістри й цифри",string.ascii_letters+string.digits),
}


def save(data):
    temporary=OUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temporary.replace(OUT)


def emit(event):
    print(json.dumps(event,ensure_ascii=False),flush=True)


def scan(alphabet, width, deadline, label):
    expected=alphabet[-1]*width
    target=hashlib.md5(expected.encode("ascii")).digest()
    began=perf_counter()
    tick=began
    md5=hashlib.md5
    attempts=0
    recovered=None
    # Перевірка дедлайну не на кожній спробі: блоки по 1 000 000 кандидатів.
    words=itertools.product(alphabet,repeat=width)
    stop=False
    while not stop:
        batch=itertools.islice(words,1_000_000)
        count=0
        for chars in batch:
            candidate="".join(chars)
            count+=1
            if md5(candidate.encode("ascii")).digest()==target:
                recovered=candidate
                stop=True
                break
        attempts+=count
        now=perf_counter()
        if now-tick>=20:
            emit({"event":"progress","alphabet":label,"width":width,"attempts":attempts,
                "total":len(alphabet)**width,"seconds":round(now-began,3)})
            tick=now
        if count<1_000_000 or now>=deadline:
            stop=True
    seconds=perf_counter()-began
    complete=recovered==expected and attempts==len(alphabet)**width
    return {"attempts":attempts,"seconds":seconds,"recovered":recovered,
        "expected":expected,"target_md5":target.hex(),"complete":complete,
        "rate_per_second":attempts/seconds,"deadline_reached":not complete and perf_counter()>=deadline}


def warmup(number):
    for i in range(30_000):
        hashlib.md5(str(i).encode("ascii")).digest()
    return os.getpid()


def prefix_scan(task):
    alphabet,width,prefix,target,deadline=task
    md5=hashlib.md5
    attempts=0
    recovered=None
    iterator=itertools.product(alphabet,repeat=width-1)
    while True:
        count=0
        for chars in itertools.islice(iterator,100_000):
            candidate=prefix+"".join(chars)
            count+=1
            if md5(candidate.encode("ascii")).digest()==target:
                recovered=candidate
        attempts+=count
        if count<100_000 or perf_counter()>=deadline:
            break
    return attempts,recovered


def parallel_run(workers, deadline):
    alphabet=ALPHABETS["mixed_digits"][1]
    width=4
    expected=alphabet[-1]*width
    target=hashlib.md5(expected.encode("ascii")).digest()
    samples=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        warmed=set(pool.map(warmup,range(workers*2)))
        for repeat in range(3):
            began=perf_counter()
            tasks=[(alphabet,width,prefix,target,deadline) for prefix in alphabet]
            results=list(pool.map(prefix_scan,tasks))
            elapsed=perf_counter()-began
            attempts=sum(r[0] for r in results)
            recovered=[r[1] for r in results if r[1] is not None]
            complete=attempts==62**4 and recovered==[expected]
            samples.append({"repeat":repeat+1,"attempts":attempts,"seconds":elapsed,"complete":complete})
            emit({"event":"parallel","workers":workers,**samples[-1]})
            if perf_counter()>=deadline: break
    values=[r["seconds"] for r in samples]
    return {"workers":workers,"alphabet_id":"mixed_digits","width":width,"space":62**4,
        "warmup_processes_observed":len(warmed),"samples":samples,
        "median_seconds":statistics.median(values),"complete":all(r["complete"] for r in samples),
        "includes_process_startup":False,"includes_job_dispatch_and_collection":True}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--max-seconds",type=int,default=1500)
    args=parser.parse_args()
    if not 1<=args.max_seconds<=1800: parser.error("Ліміт: від 1 до 1800 секунд")
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"): stream.reconfigure(encoding="utf-8")
    began=perf_counter()
    deadline=began+args.max_seconds
    machine_file=ROOT/"docs/results/machine.json"
    machine=json.loads(machine_file.read_text(encoding="utf-8-sig")) if machine_file.exists() else {}
    data={"protocol_version":1,"status":"running","started_at_utc":datetime.now(timezone.utc).isoformat(),
        "time_limit_seconds":args.max_seconds,"machine":machine,
        "runtime":{"python":sys.version,"platform":platform.platform(),"logical_cpus":os.cpu_count(),
            "hash_backend":"hashlib MD5, двійкове порівняння digest", "timer":"time.perf_counter"},
        "method":"Кожна ціль — останнє слово лексикографічного перебору заданого алфавіту.",
        "notes":["Реальний CPU-перебір із генерацією, ASCII-кодуванням, MD5 і порівнянням.",
            "Вимірюється найгірший випадок, а не середній випадок випадкового пароля.",
            "Паралельний дослід виконує той самий обсяг роботи 62**4 для 1–16 процесів.",
            "Запуск процесів і прогрівання вилучено з паралельного таймера; диспетчеризація включена.",
            "Графіки та Word/PDF будуються після CPU-експериментів.",
            "Windows використовується звичайно: частоти CPU не фіксуються, фонове навантаження не ізольовано."],
        "serial":[],"parallel":[]}
    save(data)
    # Короткі повні простори: три повтори кожного випадку.
    cases=[]
    for key in ALPHABETS:
        widths=range(1,5) if key!="digits" else range(3,8)
        cases.extend((key,width,3) for width in widths)
    # Для простору >10 млн довгі повні прогони мають один повтор.
    cases += [("lower",5,3),("upper",5,3),("lower_digits",5,1)]
    for key,width,repeats in cases:
        if perf_counter()>=deadline: break
        label,alphabet=ALPHABETS[key]
        samples=[]
        for repeat in range(repeats):
            row=scan(alphabet,width,deadline,label)
            samples.append(row)
            emit({"event":"serial","alphabet":label,"width":width,"repeat":repeat+1,
                  "attempts":row["attempts"],"seconds":round(row["seconds"],6),"complete":row["complete"]})
            if not row["complete"]: break
        data["serial"].append({"alphabet_id":key,"label":label,"alphabet":alphabet,"alphabet_size":len(alphabet),
            "width":width,"space":len(alphabet)**width,"entropy_uniform_bits":width*math.log2(len(alphabet)),
            "samples":samples,"median_seconds":statistics.median(r["seconds"] for r in samples),
            "complete":all(r["complete"] for r in samples)})
        save(data)
    for workers in (1,2,4,8,16):
        if perf_counter()>=deadline: break
        data["parallel"].append(parallel_run(workers,deadline)); save(data)
    # Найбільші простори: до мільярда кандидатів, без екстраполяції.
    for key,width in [("lower",6),("mixed",5),("mixed_digits",5)]:
        if perf_counter()>=deadline: break
        label,alphabet=ALPHABETS[key]
        emit({"event":"long_case_started","alphabet":label,"width":width,"space":len(alphabet)**width})
        row=scan(alphabet,width,deadline,label)
        data["serial"].append({"alphabet_id":key,"label":label,"alphabet":alphabet,"alphabet_size":len(alphabet),
            "width":width,"space":len(alphabet)**width,"entropy_uniform_bits":width*math.log2(len(alphabet)),
            "samples":[row],"median_seconds":row["seconds"],"complete":row["complete"]})
        emit({"event":"long_case_done","alphabet":label,"width":width,"attempts":row["attempts"],
            "seconds":round(row["seconds"],3),"complete":row["complete"]})
        save(data)
    data["elapsed_seconds"]=perf_counter()-began
    data["finished_at_utc"]=datetime.now(timezone.utc).isoformat()
    data["status"]="completed" if perf_counter()<deadline else "time_limit_reached"
    data["total_hash_operations"]=sum(s["attempts"] for r in data["serial"] for s in r["samples"])+sum(s["attempts"] for r in data["parallel"] for s in r["samples"])
    save(data)
    emit({"event":"finished","status":data["status"],"elapsed_seconds":round(data["elapsed_seconds"],3),
        "hash_operations":data["total_hash_operations"],"serial_cases":len(data["serial"]),"parallel_cases":len(data["parallel"])})


if __name__=="__main__":
    main()
