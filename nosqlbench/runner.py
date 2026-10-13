from __future__ import annotations

import random
import sys
import threading
import time
from array import array

import numpy as np
from .docs import DocFactory
from .generators import AckCounter, build_key, make_chooser
from .workloads import INSERT, MAX_SCAN_LENGTH, READ, RMW, SCAN, UPDATE, Workload


def load_phase(adapter, records: int, factory: DocFactory, seed: int, batch_size: int = 500) -> float:
    """Memuat `records` dokumen (kunci 0..records-1 ter-hash). Mengembalikan detik."""
    rng = random.Random(seed)
    t0 = time.perf_counter()
    batch = []
    for n in range(records):
        batch.append((build_key(n), factory.fields(rng)))
        if len(batch) >= batch_size:
            adapter.load_batch(batch)
            batch = []
    if batch:
        adapter.load_batch(batch)
    return time.perf_counter() - t0


def run_phase(adapter, wl: Workload, records: int, operations: int, threads: int,
              factory: DocFactory, seed: int) -> dict:
    """Menjalankan `operations` operasi dibagi rata ke `threads` thread."""
    counter = AckCounter(records)
    chooser = make_chooser(wl.request_distribution, records, counter)
    scan_key_chooser = make_chooser("zipfian", records)  # E: kunci awal scan ~ zipfian
    pick_op = wl.chooser()

    per_thread = [operations // threads + (1 if i < operations % threads else 0)
                  for i in range(threads)]
    lat = [{} for _ in range(threads)]
    errors = [0] * threads
    first_err: list = []
    err_lock = threading.Lock()

    def execute(op: str, rng: random.Random):
        if op == READ:
            if adapter.read(build_key(chooser.next(rng))) is None:
                raise KeyError("dokumen tidak ditemukan")
        elif op == UPDATE:
            adapter.update(build_key(chooser.next(rng)), factory.one_field(rng))
        elif op == INSERT:
            n = counter.next()
            adapter.insert(build_key(n), factory.fields(rng))
            counter.acknowledge(n)
        elif op == SCAN:
            start = build_key(scan_key_chooser.next(rng))
            adapter.scan(start, rng.randint(1, MAX_SCAN_LENGTH))
        elif op == RMW:
            key = build_key(chooser.next(rng))
            if adapter.read(key) is None:
                raise KeyError("dokumen tidak ditemukan")
            adapter.update(key, factory.one_field(rng))
        else:  # pragma: no cover
            raise ValueError(op)

    def worker(tid: int, n_ops: int):
        rng = random.Random(seed * 100_003 + tid)
        mine = lat[tid]
        for _ in range(n_ops):
            op = pick_op(rng)
            t0 = time.perf_counter_ns()
            try:
                execute(op, rng)
            except Exception as e:  # noqa: BLE001
                errors[tid] += 1
                with err_lock:
                    if len(first_err) < 5:
                        first_err.append(f"{op}: {type(e).__name__}: {e}")
                continue
            mine.setdefault(op, array("d")).append((time.perf_counter_ns() - t0) / 1e6)

    ts = [threading.Thread(target=worker, args=(i, per_thread[i])) for i in range(threads)]
    t0 = time.perf_counter()
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    runtime = time.perf_counter() - t0

    for msg in first_err:
        print(f"    [galat] {msg}", file=sys.stderr)

    per_op = {}
    ops_all = {op for d in lat for op in d}
    ok_total = 0
    for op in sorted(ops_all):
        arr = np.concatenate([np.frombuffer(d[op], dtype=np.float64) for d in lat if op in d])
        ok_total += len(arr)
        per_op[op] = {"count": int(len(arr)), "avg_ms": float(arr.mean()),
                      "p50_ms": float(np.percentile(arr, 50)),
                      "p95_ms": float(np.percentile(arr, 95)),
                      "p99_ms": float(np.percentile(arr, 99)),
                      "max_ms": float(arr.max())}
    return {"runtime_s": runtime, "operations": operations, "ok_ops": ok_total,
            "errors": int(sum(errors)),
            "throughput_ops_s": ok_total / runtime if runtime > 0 else 0.0,
            "per_op": per_op}