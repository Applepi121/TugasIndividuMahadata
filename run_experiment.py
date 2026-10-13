from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime

from nosqlbench import envinfo
from nosqlbench.adapters import make_adapter
from nosqlbench.docs import DocFactory
from nosqlbench.runner import load_phase, run_phase
from nosqlbench.workloads import EXECUTION_ORDER, WORKLOADS

RUN_FIELDS = ["timestamp", "db", "workload", "records", "operations", "threads", "repeat",
              "load_s", "runtime_s", "throughput_ops_s", "ok_ops", "errors"]
LAT_FIELDS = ["db", "workload", "records", "threads", "repeat", "op", "count",
              "avg_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms"]


def parse_args():
    e = os.environ.get
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", nargs="+", default=["mongodb", "couchdb"],
                   choices=["mongodb", "couchdb", "couchbase", "memory"])
    p.add_argument("--records", nargs="+", type=int, default=[10_000],
                   help="jumlah record awal (artikel: 100k, 1M, 10M; versi laptop: 10k, 100k, 1M)")
    p.add_argument("--threads", nargs="+", type=int, default=[1, 3, 6])
    p.add_argument("--workloads", nargs="+", default=list("ABCDEFGH"), choices=list("ABCDEFGH"))
    p.add_argument("--repeats", type=int, default=3, help="ulangan per konfigurasi (artikel: 3)")
    p.add_argument("--ops-ratio", type=float, default=1.0,
                   help="operationcount = ops-ratio x records (asumsi: 1.0)")
    p.add_argument("--reload-mode", choices=["smart", "every-run"], default="smart",
                   help="smart: muat ulang hanya saat ukuran baru / setelah workload ber-insert (D,E); "
                        "every-run: muat ulang sebelum setiap run (paling setia YCSB, paling lambat)")
    p.add_argument("--batch-size", type=int, default=500, help="ukuran batch fase load")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="results")
    p.add_argument("--resume", action="store_true", help="lewati run yang sudah ada di runs.csv")
    p.add_argument("--mongo-uri", default=e("MONGO_URI", "mongodb://127.0.0.1:27017"))
    p.add_argument("--couchdb-url", default=e("COUCHDB_URL", "http://127.0.0.1:5984"))
    p.add_argument("--couchdb-user", default=e("COUCHDB_USER", "admin"))
    p.add_argument("--couchdb-password", default=e("COUCHDB_PASSWORD", "password"))
    p.add_argument("--couchbase-host", default=e("COUCHBASE_HOST", "127.0.0.1"))
    p.add_argument("--couchbase-user", default=e("COUCHBASE_USER", "Administrator"))
    p.add_argument("--couchbase-password", default=e("COUCHBASE_PASSWORD", "password"))
    return p.parse_args()


def append_rows(path, fields, rows):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerows(rows)


def done_keys(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="") as f:
        return {(r["db"], r["workload"], int(r["records"]), int(r["threads"]), int(r["repeat"]))
                for r in csv.DictReader(f)}


def main():
    a = parse_args()
    os.makedirs(a.out, exist_ok=True)
    runs_csv, lat_csv = os.path.join(a.out, "runs.csv"), os.path.join(a.out, "latency.csv")
    done = done_keys(runs_csv) if a.resume else set()
    factory = DocFactory(seed=a.seed)
    cfg = vars(a)
    cfg = {k.replace("-", "_"): v for k, v in cfg.items()}
    order = [w for w in EXECUTION_ORDER if w in a.workloads]
    max_threads = max(a.threads)
    db_infos = {}

    for dbname in a.db:
        adapter = make_adapter(dbname, max_threads, cfg)
        db_infos[dbname] = adapter.info()
        print(f"\n=== {dbname}: {db_infos[dbname].get('server', '')} ===")
        for records in a.records:
            operations = int(records * a.ops_ratio)
            loaded, load_s = False, None
            for wl_name in order:
                wl = WORKLOADS[wl_name]
                for threads in a.threads:
                    for rep in range(1, a.repeats + 1):
                        key = (dbname, wl_name, records, threads, rep)
                        if key in done:
                            continue
                        if (not loaded) or a.reload_mode == "every-run":
                            adapter.prepare()
                            load_s = load_phase(adapter, records, factory, a.seed, a.batch_size)
                            loaded = True
                            print(f"  [load] {records} record: {load_s:.1f} s")
                        else:
                            load_s = None
                        res = run_phase(adapter, wl, records, operations, threads, factory,
                                        seed=a.seed + rep)
                        if wl.has_inserts:
                            loaded = False  # data bertambah -> muat ulang untuk run berikutnya
                        print(f"  {dbname:9s} N={records:<9d} WL={wl_name} thr={threads} rep={rep}: "
                              f"{res['runtime_s']:9.2f} s  {res['throughput_ops_s']:9.0f} ops/s  "
                              f"galat={res['errors']}")
                        append_rows(runs_csv, RUN_FIELDS, [{
                            "timestamp": datetime.now().isoformat(timespec="seconds"),
                            "db": dbname, "workload": wl_name, "records": records,
                            "operations": operations, "threads": threads, "repeat": rep,
                            "load_s": "" if load_s is None else f"{load_s:.3f}",
                            "runtime_s": f"{res['runtime_s']:.4f}",
                            "throughput_ops_s": f"{res['throughput_ops_s']:.2f}",
                            "ok_ops": res["ok_ops"], "errors": res["errors"]}])
                        append_rows(lat_csv, LAT_FIELDS, [{
                            "db": dbname, "workload": wl_name, "records": records,
                            "threads": threads, "repeat": rep, "op": op,
                            **{k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in s.items()}}
                            for op, s in res["per_op"].items()])
        adapter.close()

    with open(os.path.join(a.out, "env.json"), "w") as f:
        json.dump({"generated": datetime.now().isoformat(timespec="seconds"),
                   "args": {k: v for k, v in vars(a).items() if "password" not in k},
                   "env": envinfo.collect(db_infos)}, f, indent=2, ensure_ascii=False)
    print(f"\nSelesai. Hasil: {runs_csv}")


if __name__ == "__main__":
    sys.exit(main())