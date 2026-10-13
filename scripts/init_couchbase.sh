#!/usr/bin/env bash
# Inisialisasi klaster Couchbase satu node (jalankan sekali setelah container hidup).
set -euo pipefail
docker compose --profile couchbase exec couchbase couchbase-cli cluster-init \
  --cluster localhost --cluster-username Administrator --cluster-password password \
  --services data,index,query --cluster-ramsize 2048 --cluster-index-ramsize 512
echo "Couchbase siap. Bucket 'ycsb' dibuat otomatis oleh run_experiment.py."