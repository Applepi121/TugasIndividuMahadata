# Replikasi Parsial: Performance Evaluation of NoSQL Document Databases (YCSB)

Eksperimen mandiri Mahadata (IF25-40402) berdasarkan artikel:

> Carvalho, I., Sá, F., & Bernardino, J. (2023). Performance evaluation of NoSQL document databases: Couchbase, CouchDB, and MongoDB. *Algorithms, 16*(2), 78. https://doi.org/10.3390/a16020078

Tingkat replikasi: **parsial + skala laptop** (panduan 4.1). Artikel memakai 100k/1M/10M record; di sini
10k/100k/1M (tetap kelipatan 10) agar muat di laptop. Pola perbandingan (peringkat DB, scale-up thread,
kenaikan runtime, dampak workload scan E) dibandingkan dengan artikel, bukan angka absolutnya.

## Isi repositori
| Berkas | Fungsi |
|---|---|
| `nosqlbench/workloads.py` | Workload A–H persis Tabel 1 artikel (20 field × 500 B = 10 KB/dokumen) |
| `nosqlbench/generators.py` | Zipfian, scrambled Zipfian, latest, uniform (algoritma YCSB) |
| `nosqlbench/adapters.py` | Adapter MongoDB, CouchDB, Couchbase (eksperimental), Memory (uji) |
| `nosqlbench/runner.py` | Fase load + fase transaksi multi-thread, latensi per operasi |
| `run_experiment.py` | Menjalankan DB × ukuran × thread × workload × ulangan → `results/*.csv` |
| `analyze.py` | Tabel, grafik, dan perbandingan dengan artikel → `results/.../report/` |
| `nosqlbench/paper_reference.py` | Angka Tabel 2–7 artikel |
| `tests/` | 11 uji unit (generator, workload, runner, adapter CouchDB vs server palsu) |

## Menjalankan
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d mongodb couchdb          # Couchbase: lihat bawah
python -m unittest discover -s tests -v       # uji logika harness
bash scripts/run_quick.sh                     # uji cepat (10k record)
bash scripts/run_scaled.sh                    # eksperimen utama (10k, 100k, 1M)
```
Atau manual: `python run_experiment.py --db mongodb couchdb --records 10000 100000 --threads 1 3 6 --repeats 3`.
Proses dapat dilanjutkan dengan `--resume`. Lingkungan (CPU, RAM, versi DB & pustaka) tercatat di `results/*/env.json`.
Opsi memuat ulang data: `--reload-mode smart` (bawaan: muat ulang saat ukuran baru dan setelah workload D/E yang menambah data) atau `every-run` (paling setia YCSB, lebih lambat).

Couchbase (opsional): `docker compose --profile couchbase up -d couchbase && bash scripts/init_couchbase.sh`,
`pip install couchbase`, lalu `--db couchbase`. **Adapter ini belum diuji** terhadap server asli; periksa dulu pada 1.000 record.

Kebutuhan disk kasar: ±10 KB × record per DB (1M record ≈ 10 GB; CouchDB bisa 2× karena append-only).

## Deviasi dari artikel (cantumkan di laporan bagian B)
1. **Harness Python, bukan YCSB Java.** YCSB tidak punya binding CouchDB, sehingga ketiga DB memakai harness yang sama agar adil. Konsekuensi: overhead klien Python (GIL) lebih besar; hasil absolut tidak sebanding dengan artikel.
2. Skala data 10k/100k/1M (artikel 100k/1M/10M); `operationcount = recordcount` (asumsi; artikel tidak menyebut eksplisit).
3. Fase load memakai batch (`insert_many`, `_bulk_docs`) demi kecepatan; runtime yang dibandingkan adalah **fase transaksi** saja.
4. Nilai field diambil dari kolam 2048 string acak (lebih kompresibel daripada acak murni).
5. Distribusi `latest` memakai zeta tetap atas jumlah record awal (YCSB memperbarui zeta inkremental).
6. CouchDB: `q=1` shard, update = GET lalu PUT `_rev` (retry bila konflik 409). Mongo: `$set` satu field.
7. Perangkat keras & OS berbeda (artikel: Ryzen 5 4500U, 6 core, Windows 10); gunakan satu mesin dan tutup aplikasi lain.
8. Cache OS tidak dikosongkan antar-run; urutan workload memberi data "hangat" pada beberapa run.

## Catatan temuan pada artikel
Gambar 6/Tabel 8 memakai 297,30 s sebagai total MongoDB 100k record, padahal itu nilai 1 thread (total Tabel 7 = 550,56 s). Kesimpulan peringkat tidak berubah (lihat `paper_reference.py`).

## Integritas akademik
Algoritma generator mengikuti YCSB (Cooper et al., 2010). Panduan tugas (bagian 6) mewajibkan pernyataan penggunaan generative AI bila diizinkan dosen: kode awal repositori ini dibantu AI; Anda harus memahami dan mampu menjelaskan setiap bagian serta menjalankan eksperimen sendiri. Jangan merekayasa hasil; hasil berbeda dari artikel tetap sah bila dijelaskan.

## Status verifikasi
Diuji: seluruh uji unit lulus; `run_experiment.py` + `analyze.py` berjalan end-to-end dengan adapter Memory; adapter CouchDB diuji terhadap server CouchDB palsu. **Belum diuji terhadap MongoDB/CouchDB/Couchbase asli.**