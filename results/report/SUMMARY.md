# Ringkasan hasil eksperimen

**Peringatan:** terdapat operasi galat (lihat kolom errors di runs.csv):

| db | records | errors |
|---|---|---|
| mongodb | 10000 | 832412 |

**Catatan:** konfigurasi berikut belum memuat semua workload A-H; total runtime di bawah merupakan jumlah workload yang tersedia saja.

| db | records | threads | n_wl |
|---|---|---|---|
| couchdb | 10000 | 1 | 1 |

## Total runtime semua workload (detik), analog Tabel 3, 5, 7 artikel

### CouchDB

| Thread | 10.000 record |
|---|---|
| 1 | 942.84 |
| Total | 942.84 |

### MongoDB

| Thread | 10.000 record |
|---|---|
| 1 | 93.36 |
| 3 | 32.65 |
| 6 | 28.50 |
| Total | 154.51 |

## Scale-up terhadap jumlah thread

| db | records | turun_1_ke_3_% | speedup_3 | turun_3_ke_6_% | speedup_6 |
|---|---|---|---|---|---|
| CouchDB | 10000 |  |  |  |  |
| MongoDB | 10000 | 65.03 | 2.86 | 12.73 | 3.28 |

## Workload E (scan) vs workload lain (jumlah semua thread, detik)

| db | records | workload_E_s | tanpa_E_s |
|---|---|---|---|
| CouchDB | 10000 | 0.00 | 942.84 |
| MongoDB | 10000 | 27.04 | 127.47 |

## DB tercepat per workload (3 thread)

**Eksperimen ini**

| records | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| 10000 | MongoDB | MongoDB | MongoDB | MongoDB | MongoDB | MongoDB | MongoDB | MongoDB |

**Artikel** (hanya membandingkan CouchDB, MongoDB)

| records (artikel) | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| 100000 | CouchDB | MongoDB | MongoDB | MongoDB | MongoDB | MongoDB | MongoDB | MongoDB |
| 1000000 | MongoDB | MongoDB | MongoDB | MongoDB | CouchDB | MongoDB | MongoDB | CouchDB |
| 10000000 | MongoDB | MongoDB | MongoDB | MongoDB | CouchDB | MongoDB | MongoDB | CouchDB |

## Perbandingan dengan temuan utama artikel

Faktor kenaikan runtime pada pertambahan data 10x (artikel; ukuran data berbeda dari eksperimen ini):

| db | dari (artikel) | ke (artikel) | faktor_runtime_artikel |
|---|---|---|---|
| CouchDB | 100000 | 1000000 | 17.90 |
| CouchDB | 1000000 | 10000000 | 18.08 |
| MongoDB | 100000 | 1000000 | 37.42 |
| MongoDB | 1000000 | 10000000 | 23.79 |

Scale-up pada artikel (dihitung dari Tabel 3, 5, 7):

| db | records | turun_1_ke_3_% | turun_3_ke_6_% | speedup_6 |
|---|---|---|---|---|
| CouchDB | 100000 | 57.67 | 22.65 | 3.05 |
| CouchDB | 1000000 | 41.99 | 44.51 | 3.11 |
| CouchDB | 10000000 | 40.30 | 50.18 | 3.36 |
| MongoDB | 100000 | 53.63 | 16.28 | 2.58 |
| MongoDB | 1000000 | 31.25 | 8.15 | 1.58 |
| MongoDB | 10000000 | 23.32 | 6.26 | 1.39 |

Pemeriksaan klaim artikel pada data eksperimen ini (K1: MongoDB tercepat kecuali scan; K2: CouchDB lebih cepat pada scan workload E). Artikel melaporkan rasio CouchDB/MongoDB tanpa E sebesar 3,28x dan MongoDB/CouchDB pada E sebesar 3,10x (total semua ukuran data):

| records | K1: MongoDB lebih cepat dari CouchDB (tanpa E) | rasio CouchDB/MongoDB tanpa E | K2: CouchDB lebih cepat dari MongoDB pada E (scan) | rasio MongoDB/CouchDB pada E |
|---|---|---|---|---|
| 10000 | ya | 7.40 | ya |  |
