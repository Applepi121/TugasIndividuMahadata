#!/usr/bin/env bash
# Replikasi parsial berskala laptop: 10k, 100k, 1M record (kelipatan 10 seperti artikel),
# 1/3/6 thread, 8 workload, 3 ulangan. Perkiraan data: 1M record ~ 10 GB per DB.
# Dapat dihentikan dan dilanjutkan (--resume). Hapus "1000000" bila disk/waktu terbatas.
set -euo pipefail
python run_experiment.py --db mongodb couchdb --records 10000 100000 1000000 \
  --threads 1 3 6 --repeats 3 --resume --out results/scaled
python analyze.py --results results/scaled