from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from nosqlbench.paper_reference import (PAPER_SIZES, THREE_THREADS_BY_WORKLOAD,
                                        TOTAL_BY_THREADS)

COLORS = {"couchbase": "#D55E00", "couchdb": "#E69F00", "mongodb": "#009E73", "memory": "#7F7F7F"}
LABEL = {"couchbase": "Couchbase", "couchdb": "CouchDB", "mongodb": "MongoDB", "memory": "Memory"}
DB_ORDER = ["couchbase", "couchdb", "mongodb", "memory"]
ALL_WL = list("ABCDEFGH")


def md_table(df: pd.DataFrame, floatfmt="{:,.2f}") -> str:
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else floatfmt.format(v))
    cols = [str(c) for c in d.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in d.iterrows():
        lines.append("| " + " | ".join(str(v) for v in r.values) + " |")
    return "\n".join(lines)


def dbs_in(df):
    return [d for d in DB_ORDER if d in set(df.db)]


def fmt_n(n):
    return f"{n:,}".replace(",", ".")


def save_fig(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = a.out or os.path.join(a.results, "report")
    os.makedirs(out, exist_ok=True)

    runs = pd.read_csv(os.path.join(a.results, "runs.csv"))
    lat_path = os.path.join(a.results, "latency.csv")
    lat = pd.read_csv(lat_path) if os.path.exists(lat_path) else None
    md = ["# Ringkasan hasil eksperimen\n"]

    # ---- 0. Kualitas data -------------------------------------------------- #
    err = runs.groupby(["db", "records"]).errors.sum().reset_index()
    if err.errors.sum() > 0:
        md.append("**Peringatan:** terdapat operasi galat (lihat kolom errors di runs.csv):\n")
        md.append(md_table(err[err.errors > 0], "{:,.0f}") + "\n")

    # ---- 1. Rata-rata & simpangan baku antar ulangan ---------------------- #
    g = (runs.groupby(["db", "records", "threads", "workload"]).runtime_s
         .agg(mean="mean", std="std", n="count").reset_index())
    g.to_csv(os.path.join(out, "runtime_per_workload.csv"), index=False)

    # kelengkapan: total hanya bermakna bila A-H lengkap
    comp = g.groupby(["db", "records", "threads"]).workload.nunique().reset_index(name="n_wl")
    incomplete = comp[comp.n_wl < 8]
    if len(incomplete):
        md.append("**Catatan:** konfigurasi berikut belum memuat semua workload A-H; "
                  "total runtime di bawah merupakan jumlah workload yang tersedia saja.\n")
        md.append(md_table(incomplete, "{:,.0f}") + "\n")

    # ---- 2. Total runtime (analog Tabel 3, 5, 7) --------------------------- #
    tot = g.groupby(["db", "records", "threads"])["mean"].sum().reset_index(name="total_s")
    tot.to_csv(os.path.join(out, "total_runtime_by_threads.csv"), index=False)
    md.append("## Total runtime semua workload (detik), analog Tabel 3, 5, 7 artikel\n")
    for db in dbs_in(tot):
        pv = tot[tot.db == db].pivot(index="threads", columns="records", values="total_s")
        pv.columns = [fmt_n(c) + " record" for c in pv.columns]
        pv.loc["Total"] = pv.sum()
        md.append(f"### {LABEL[db]}\n")
        md.append(md_table(pv.reset_index().rename(columns={"threads": "Thread"}).astype({"Thread": str})) + "\n")

    size_tot = tot.groupby(["db", "records"]).total_s.sum().reset_index()
    size_tot.to_csv(os.path.join(out, "total_runtime_by_size.csv"), index=False)

    # ---- 3. Faktor kenaikan antar ukuran data (tenfold) -------------------- #
    sizes = sorted(runs.records.unique())
    growth_rows = []
    for db in dbs_in(size_tot):
        s = size_tot[size_tot.db == db].set_index("records").total_s
        for lo, hi in zip(sizes[:-1], sizes[1:]):
            if lo in s.index and hi in s.index:
                growth_rows.append({"db": LABEL[db], "dari": lo, "ke": hi,
                                    "faktor_data": hi / lo, "faktor_runtime": s[hi] / s[lo]})
    growth = pd.DataFrame(growth_rows)
    if len(growth):
        growth.to_csv(os.path.join(out, "growth_factors.csv"), index=False)
        md.append("## Kenaikan runtime saat data bertambah (harapan linier = faktor data)\n")
        md.append(md_table(growth) + "\n")

    # ---- 4. Scale-up terhadap thread --------------------------------------- #
    sc_rows = []
    for (db, n), d in tot.groupby(["db", "records"]):
        t = d.set_index("threads").total_s
        row = {"db": LABEL[db], "records": n}
        if {1, 3} <= set(t.index):
            row["turun_1_ke_3_%"] = 100 * (1 - t[3] / t[1])
            row["speedup_3"] = t[1] / t[3]
        if {3, 6} <= set(t.index):
            row["turun_3_ke_6_%"] = 100 * (1 - t[6] / t[3])
        if {1, 6} <= set(t.index):
            row["speedup_6"] = t[1] / t[6]
        sc_rows.append(row)
    sc = pd.DataFrame(sc_rows)
    if len(sc):
        sc.to_csv(os.path.join(out, "scaleup.csv"), index=False)
        md.append("## Scale-up terhadap jumlah thread\n")
        md.append(md_table(sc.astype({"records": str})) + "\n")

    # ---- 5. Workload E vs lainnya (analog Gambar 7-8, Tabel 9-10) ---------- #
    e_rows = []
    for db in dbs_in(g):
        for n in sizes:
            d = g[(g.db == db) & (g.records == n)]
            tE = d[d.workload == "E"]["mean"].sum()
            tO = d[d.workload != "E"]["mean"].sum()
            e_rows.append({"db": LABEL[db], "records": n, "workload_E_s": tE, "tanpa_E_s": tO})
    ed = pd.DataFrame(e_rows)
    ed.to_csv(os.path.join(out, "workload_E_vs_others.csv"), index=False)
    md.append("## Workload E (scan) vs workload lain (jumlah semua thread, detik)\n")
    md.append(md_table(ed.astype({"records": str})) + "\n")

    # ---- 6. Pemenang per workload (3 thread) vs artikel -------------------- #
    thr_ref = 3 if 3 in set(runs.threads) else sorted(runs.threads)[0]
    win_rows = []
    for i, n in enumerate(sizes):
        row = {"records": n}
        for w in ALL_WL:
            d = g[(g.records == n) & (g.threads == thr_ref) & (g.workload == w)]
            row[w] = LABEL[d.loc[d["mean"].idxmin(), "db"]] if len(d) else "-"
        win_rows.append(row)
    win = pd.DataFrame(win_rows)
    # artikel: DB tercepat per workload pada 3 thread (hanya DB yang ada pada eksperimen kita)
    avail = [d for d in ("couchbase", "couchdb", "mongodb") if d in set(runs.db)]
    paper_rows = []
    for i, n in enumerate(PAPER_SIZES):
        row = {"records (artikel)": n}
        for w in ALL_WL:
            vals = {d: THREE_THREADS_BY_WORKLOAD[d][w][i] for d in avail}
            row[w] = LABEL[min(vals, key=vals.get)] if vals else "-"
        paper_rows.append(row)
    pw = pd.DataFrame(paper_rows)
    win.to_csv(os.path.join(out, "winner_per_workload.csv"), index=False)
    pw.to_csv(os.path.join(out, "winner_per_workload_paper.csv"), index=False)
    md.append(f"## DB tercepat per workload ({thr_ref} thread)\n")
    md.append("**Eksperimen ini**\n")
    md.append(md_table(win.astype({"records": str})) + "\n")
    md.append(f"**Artikel** (hanya membandingkan {', '.join(LABEL[d] for d in avail)})\n")
    md.append(md_table(pw.astype({"records (artikel)": str})) + "\n")

    # ---- 7. Perbandingan terhadap temuan artikel --------------------------- #
    md.append("## Perbandingan dengan temuan utama artikel\n")
    paper_growth = []
    for db in avail:
        s = {n: sum(TOTAL_BY_THREADS[db][n].values()) for n in PAPER_SIZES}
        for lo, hi in zip(PAPER_SIZES[:-1], PAPER_SIZES[1:]):
            paper_growth.append({"db": LABEL[db], "dari (artikel)": lo, "ke (artikel)": hi,
                                 "faktor_runtime_artikel": s[hi] / s[lo]})
    pg = pd.DataFrame(paper_growth)
    pg.to_csv(os.path.join(out, "growth_factors_paper.csv"), index=False)
    md.append("Faktor kenaikan runtime pada pertambahan data 10x (artikel; ukuran data berbeda dari eksperimen ini):\n")
    md.append((md_table(pg.astype({"dari (artikel)": str, "ke (artikel)": str})) if len(pg) else "(tidak ada DB pembanding)") + "\n")

    psc = []
    for db in avail:
        for n in PAPER_SIZES:
            t = TOTAL_BY_THREADS[db][n]
            psc.append({"db": LABEL[db], "records": n,
                        "turun_1_ke_3_%": 100 * (1 - t[3] / t[1]),
                        "turun_3_ke_6_%": 100 * (1 - t[6] / t[3]),
                        "speedup_6": t[1] / t[6]})
    psc = pd.DataFrame(psc)
    psc.to_csv(os.path.join(out, "scaleup_paper.csv"), index=False)
    md.append("Scale-up pada artikel (dihitung dari Tabel 3, 5, 7):\n")
    md.append((md_table(psc.astype({"records": str})) if len(psc) else "(tidak ada DB pembanding)") + "\n")

    # Pemeriksaan klaim kualitatif
    claims = []
    if {"mongodb", "couchdb"} <= set(runs.db):
        for n in sizes:
            d = g[g.records == n]
            def tt(db, excl_e):
                x = d[(d.db == db)]
                x = x[x.workload != "E"] if excl_e else x[x.workload == "E"]
                return x["mean"].sum()
            m_o, c_o = tt("mongodb", True), tt("couchdb", True)
            m_e, c_e = tt("mongodb", False), tt("couchdb", False)
            claims.append({"records": n,
                           "K1: MongoDB lebih cepat dari CouchDB (tanpa E)": "ya" if m_o < c_o else "tidak",
                           "rasio CouchDB/MongoDB tanpa E": c_o / m_o if m_o else np.nan,
                           "K2: CouchDB lebih cepat dari MongoDB pada E (scan)": "ya" if c_e < m_e else "tidak",
                           "rasio MongoDB/CouchDB pada E": m_e / c_e if c_e else np.nan})
    if claims:
        cl = pd.DataFrame(claims)
        cl.to_csv(os.path.join(out, "claims_check.csv"), index=False)
        md.append("Pemeriksaan klaim artikel pada data eksperimen ini "
                  "(K1: MongoDB tercepat kecuali scan; K2: CouchDB lebih cepat pada scan workload E). "
                  "Artikel melaporkan rasio CouchDB/MongoDB tanpa E sebesar 3,28x dan "
                  "MongoDB/CouchDB pada E sebesar 3,10x (total semua ukuran data):\n")
        md.append(md_table(cl.astype({"records": str})) + "\n")

    # ---- 8. Latensi per operasi -------------------------------------------- #
    if lat is not None and len(lat):
        lg = (lat.groupby(["db", "records", "threads", "op"])
              .apply(lambda d: pd.Series({
                  "avg_ms": np.average(d.avg_ms, weights=d["count"]),
                  "p95_ms": d.p95_ms.mean(), "p99_ms": d.p99_ms.mean(),
                  "ops": d["count"].sum()}), include_groups=False).reset_index())
        lg.to_csv(os.path.join(out, "latency_summary.csv"), index=False)

    # ====================== GRAFIK ========================================= #
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "font.size": 10})

    def grouped_bar(ax, data, title, ylabel, log=True):
        dbs = dbs_in(data)
        x = np.arange(len(sizes))
        wbar = 0.8 / max(len(dbs), 1)
        for k, db in enumerate(dbs):
            s = data[data.db == db].set_index("records").iloc[:, -1]
            vals = [s.get(n, np.nan) for n in sizes]
            bars = ax.bar(x + k * wbar - 0.4 + wbar / 2, vals, wbar, label=LABEL[db], color=COLORS[db])
            ax.bar_label(bars, labels=[(f"{v:,.0f}" if v >= 100 else f"{v:.3g}") if not np.isnan(v) else "" for v in vals],
                         fontsize=7, padding=2)
        ax.set_xticks(x, [fmt_n(n) for n in sizes])
        ax.set_xlabel("Jumlah record")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        if log:
            ax.set_yscale("log")
        ax.legend(frameon=False)

    fig, ax = plt.subplots(figsize=(7, 4.2))
    grouped_bar(ax, size_tot, "Total runtime semua workload (jumlah 1, 3, 6 thread)", "Runtime (s, skala log)")
    save_fig(fig, os.path.join(out, "fig_total_runtime.png"))

    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    grouped_bar(axs[0], ed.assign(db=ed.db.str.lower())[["db", "records", "workload_E_s"]],
                "Workload E (scan)", "Runtime (s, skala log)")
    grouped_bar(axs[1], ed.assign(db=ed.db.str.lower())[["db", "records", "tanpa_E_s"]],
                "Semua workload kecuali E", "Runtime (s, skala log)")
    save_fig(fig, os.path.join(out, "fig_workload_E.png"))

    # scale-up: speedup vs thread
    thr = sorted(runs.threads.unique())
    fig, axs = plt.subplots(1, len(sizes), figsize=(4.2 * len(sizes), 3.8), squeeze=False, sharey=True)
    for ax, n in zip(axs[0], sizes):
        for db in dbs_in(tot):
            t = tot[(tot.db == db) & (tot.records == n)].set_index("threads").total_s
            if 1 in t.index:
                ax.plot([x for x in thr if x in t.index], [t[1] / t[x] for x in thr if x in t.index],
                        marker="o", label=LABEL[db], color=COLORS[db])
        ax.plot(thr, thr, ls=":", color="gray", label="ideal")
        ax.set_title(f"{fmt_n(n)} record")
        ax.set_xlabel("Thread")
        ax.set_xticks(thr)
    axs[0][0].set_ylabel("Speed-up (T1 / Tn)")
    axs[0][0].legend(frameon=False)
    save_fig(fig, os.path.join(out, "fig_scaleup.png"))

    # runtime per workload (thr_ref thread)
    fig, axs = plt.subplots(1, len(sizes), figsize=(4.6 * len(sizes), 3.8), squeeze=False)
    for ax, n in zip(axs[0], sizes):
        dbs = dbs_in(g)
        xx = np.arange(8)
        wbar = 0.8 / max(len(dbs), 1)
        for k, db in enumerate(dbs):
            d = g[(g.db == db) & (g.records == n) & (g.threads == thr_ref)].set_index("workload")["mean"]
            e = g[(g.db == db) & (g.records == n) & (g.threads == thr_ref)].set_index("workload")["std"]
            ax.bar(xx + k * wbar - 0.4 + wbar / 2, [d.get(w, np.nan) for w in ALL_WL], wbar,
                   yerr=[e.get(w, 0) if not pd.isna(e.get(w, 0)) else 0 for w in ALL_WL],
                   label=LABEL[db], color=COLORS[db], error_kw={"lw": 0.8})
        ax.set_xticks(xx, ALL_WL)
        ax.set_yscale("log")
        ax.set_title(f"{fmt_n(n)} record, {thr_ref} thread")
        ax.set_xlabel("Workload")
    axs[0][0].set_ylabel("Runtime (s, skala log; bar galat = SD)")
    axs[0][0].legend(frameon=False)
    save_fig(fig, os.path.join(out, "fig_per_workload.png"))

    # throughput
    tp = runs.groupby(["db", "records", "threads", "workload"]).throughput_ops_s.mean().reset_index()
    tp.to_csv(os.path.join(out, "throughput.csv"), index=False)

    with open(os.path.join(out, "SUMMARY.md"), "w") as f:
        f.write("\n".join(md))
    print(f"Laporan ditulis ke {out}/ (SUMMARY.md, *.csv, fig_*.png)")


if __name__ == "__main__":
    main()