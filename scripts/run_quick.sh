#!/usr/bin/env bash
# Uji cepat (menit): memastikan lingkungan benar. 10k record, 1 & 3 thread, 1 ulangan.
set -euo pipefail
python run_experiment.py --db mongodb couchdb --records 10000 --threads 1 3 --repeats 1 --out results/quick
python analyze.py --results results/quick