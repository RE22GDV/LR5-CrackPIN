"""GPU-перебір і незалежна перевірка MD5 через CPU hashlib."""

from datetime import datetime,timezone
import argparse
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
from time import perf_counter,sleep

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from crackpin.gpu import GPUEngine,ordinal_word
from hardware_benchmark import ALPHABETS


def save(data):
    f=ROOT/"docs/results/gpu.json"
    tmp=f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(f)


def emit(event):
    print(json.dumps(event,ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--validate-only",action="store_true")
    parser.add_argument("--wait-for-cpu",action="store_true")
    parser.add_argument("--deadline-utc",default=None)
    args=parser.parse_args()
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"): stream.reconfigure(encoding="utf-8")
    absolute=datetime.fromisoformat(args.deadline_utc) if args.deadline_utc else None
    remaining=(absolute-datetime.now(timezone.utc)).total_seconds() if absolute else 600
    deadline=perf_counter()+max(0,remaining)
    gpu=GPUEngine()
    data={"status":"validating","device":gpu.metadata(),"validated_at_utc":datetime.now(timezone.utc).isoformat(),
        "kernel":"Спеціалізований одноблоковий MD5 OpenCL; Python управляє запуском.",
        "validation":[],"cases":[],"notes":["Використано лише синтетичні навчальні паролі.",
            "GPU-ядро та CPU-Python мають однаковий простір, але різні реалізації й накладні витрати.",
            "Це прискорення стенда, а не ізольоване порівняння архітектур або мов.",
            "Компіляція ядра та прогрівання вилучені з wall_seconds; буфери, запуск і копіювання результату включені.",
            "kernel_seconds — сума апаратних профільних інтервалів усіх запусків, не загальний час програми."]}
    rng=random.Random(5009)
    for key,(label,alphabet) in ALPHABETS.items():
        for width in (1,2,3,4,5,6,8):
            count=len(alphabet)**width
            indices=sorted(set([0,1,count-1,count//2]+[rng.randrange(count) for _ in range(40)]))
            received=gpu.hashes(alphabet,width,indices)
            expected=[hashlib.md5(ordinal_word(i,alphabet,width).encode("ascii")).hexdigest() for i in indices]
            if received!=expected: raise AssertionError((key,width,"MD5 GPU не збігається з hashlib"))
            row={"alphabet_id":key,"width":width,"indices":indices,"hashes":received,"passed":len(indices)}
            data["validation"].append(row)
        emit({"event":"validation","alphabet":label,"passed":sum(v["passed"] for v in data["validation"] if v["alphabet_id"]==key)})
    data["validation_total"]=sum(r["passed"] for r in data["validation"])
    data["status"]="validated"
    save(data)
    if args.validate_only:
        emit({"event":"validated","total":data["validation_total"],"device":data["device"]}); return
    if args.wait_for_cpu:
        emit({"event":"waiting_for_cpu","validation_total":data["validation_total"]})
        while perf_counter()<deadline:
            f=ROOT/"docs/results/hardware.json"
            cpu=json.loads(f.read_text(encoding="utf-8"))
            if cpu["status"]!="running": break
            sleep(2)
        else:
            data["status"]="deadline_before_benchmark"; save(data); return
    data["status"]="running"
    data["started_at_utc"]=datetime.now(timezone.utc).isoformat()
    save(data)
    cases=[("digits",5),("digits",7),("lower",4),("upper",4),("lower_digits",4),("mixed",4),("mixed_digits",4),
           ("lower",5),("lower",6),("lower_digits",5),("mixed",5),("mixed_digits",5),("mixed_digits",6)]
    for key,width in cases:
        if perf_counter()>=deadline: break
        label,alphabet=ALPHABETS[key]
        warmup=gpu.scan(alphabet,width,deadline=deadline) # прогрівання саме цього ядра
        if not warmup["complete"] or perf_counter()>=deadline: break
        samples=[]
        for repeat in range(3):
            row=gpu.scan(alphabet,width,deadline=deadline)
            samples.append(row)
            emit({"event":"gpu","alphabet":label,"width":width,"repeat":repeat+1,"attempts":row["attempts"],
                "wall_seconds":round(row["wall_seconds"],6),"kernel_seconds":round(row["kernel_seconds"],6),"complete":row["complete"]})
            if not row["complete"] or perf_counter()>=deadline: break
        if not samples: break
        data["cases"].append({"alphabet_id":key,"label":label,"alphabet_size":len(alphabet),"width":width,
            "space":len(alphabet)**width,"samples":samples,"complete":all(r["complete"] for r in samples),
            "median_wall_seconds":statistics.median(r["wall_seconds"] for r in samples),
            "median_kernel_seconds":statistics.median(r["kernel_seconds"] for r in samples)})
        save(data)
    data["finished_at_utc"]=datetime.now(timezone.utc).isoformat()
    data["status"]="completed" if perf_counter()<deadline else "time_limit_reached"
    data["measured_hash_operations"]=sum(s["attempts"] for r in data["cases"] for s in r["samples"])
    data["warmup_in_total_operations"]=False
    save(data)
    emit({"event":"gpu_finished","status":data["status"],"cases":len(data["cases"]),"hash_operations":data["measured_hash_operations"]})


if __name__=="__main__":
    main()
