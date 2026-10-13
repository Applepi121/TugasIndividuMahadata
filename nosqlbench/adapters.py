from __future__ import annotations

import bisect
import json
import threading

class DBAdapter:
    name = "base"

    def prepare(self) -> None: raise NotImplementedError
    def load_batch(self, items) -> None: raise NotImplementedError
    def read(self, key): raise NotImplementedError
    def update(self, key, fields) -> None: raise NotImplementedError
    def insert(self, key, fields) -> None: raise NotImplementedError
    def scan(self, start_key, count): raise NotImplementedError
    def info(self) -> dict: return {}
    def close(self) -> None: pass


# --------------------------------------------------------------------------- #
# Memory (hanya untuk uji logika harness; BUKAN basis data yang diuji artikel)
# --------------------------------------------------------------------------- #
class MemoryAdapter(DBAdapter):
    name = "memory"

    def __init__(self, **_):
        self._lock = threading.Lock()
        self._docs: dict = {}
        self._keys: list = []

    def prepare(self):
        with self._lock:
            self._docs, self._keys = {}, []

    def load_batch(self, items):
        with self._lock:
            for k, f in items:
                if k not in self._docs:
                    bisect.insort(self._keys, k)
                self._docs[k] = dict(f)

    def read(self, key):
        with self._lock:
            d = self._docs.get(key)
            return dict(d) if d is not None else None

    def update(self, key, fields):
        with self._lock:
            if key not in self._docs:
                raise KeyError(key)
            self._docs[key].update(fields)

    def insert(self, key, fields):
        self.load_batch([(key, fields)])

    def scan(self, start_key, count):
        with self._lock:
            i = bisect.bisect_left(self._keys, start_key)
            return [dict(self._docs[k]) for k in self._keys[i:i + count]]


# --------------------------------------------------------------------------- #
# MongoDB (pymongo)
# --------------------------------------------------------------------------- #
class MongoAdapter(DBAdapter):
    name = "mongodb"

    def __init__(self, uri="mongodb://127.0.0.1:27017", db="ycsb", collection="usertable",
                 threads=8, **_):
        from pymongo import MongoClient  # impor lambat: dependensi opsional
        self._client = MongoClient(uri, maxPoolSize=max(threads * 2, 16),
                                   serverSelectionTimeoutMS=10_000)
        self._dbname, self._collname = db, collection
        self._coll = self._client[db][collection]

    def prepare(self):
        self._client.drop_database(self._dbname)
        self._coll = self._client[self._dbname][self._collname]
        self._coll.create_index([("_id", 1)])  # _id sudah terindeks; eksplisit demi kejelasan

    def load_batch(self, items):
        self._coll.insert_many([{"_id": k, **f} for k, f in items], ordered=False)

    def read(self, key):
        return self._coll.find_one({"_id": key})

    def update(self, key, fields):
        r = self._coll.update_one({"_id": key}, {"$set": fields})
        if r.matched_count == 0:
            raise KeyError(key)

    def insert(self, key, fields):
        self._coll.insert_one({"_id": key, **fields})

    def scan(self, start_key, count):
        return list(self._coll.find({"_id": {"$gte": start_key}}).sort("_id", 1).limit(count))

    def info(self):
        try:
            return {"server": "MongoDB " + self._client.server_info()["version"]}
        except Exception as e:  # pragma: no cover
            return {"server": f"MongoDB (tidak terbaca: {e})"}

    def close(self):
        self._client.close()


# --------------------------------------------------------------------------- #
# CouchDB (HTTP/REST via requests)
# --------------------------------------------------------------------------- #
class CouchDBAdapter(DBAdapter):
    """YCSB tidak menyertakan binding CouchDB; adapter ini setara dengan pola
    GET-lalu-PUT(_rev) yang lazim dipakai pada binding pihak ketiga."""

    name = "couchdb"

    def __init__(self, url="http://127.0.0.1:5984", user="admin", password="password",
                 db="ycsb", threads=8, shards=1, **_):
        import requests
        self._requests = requests
        self._base = url.rstrip("/")
        self._auth = (user, password)
        self._db = db
        self._shards = shards
        self._pool = max(threads * 2, 16)
        self._local = threading.local()

    def _s(self):
        s = getattr(self._local, "s", None)
        if s is None:
            from requests.adapters import HTTPAdapter
            s = self._requests.Session()
            s.auth = self._auth
            s.headers.update({"Accept": "application/json"})
            ad = HTTPAdapter(pool_connections=4, pool_maxsize=self._pool)
            s.mount("http://", ad)
            s.mount("https://", ad)
            self._local.s = s
        return s

    def _u(self, path=""):
        return f"{self._base}/{self._db}{path}"

    def prepare(self):
        s = self._s()
        r = s.delete(self._u(), timeout=300)
        if r.status_code not in (200, 202, 404):
            r.raise_for_status()
        r = s.put(self._u(), params={"q": self._shards, "n": 1}, timeout=60)
        if r.status_code not in (201, 202):
            r.raise_for_status()

    def load_batch(self, items):
        docs = [{"_id": k, **f} for k, f in items]
        r = self._s().post(self._u("/_bulk_docs"), json={"docs": docs}, timeout=300)
        r.raise_for_status()
        bad = [x for x in r.json() if x.get("error")]
        if bad:
            raise RuntimeError(f"_bulk_docs gagal untuk {len(bad)} dokumen: {bad[0]}")

    def read(self, key):
        r = self._s().get(self._u("/" + key), timeout=60)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def update(self, key, fields, retries=8):
        s = self._s()
        for _ in range(retries):
            r = s.get(self._u("/" + key), timeout=60)
            if r.status_code == 404:
                raise KeyError(key)
            r.raise_for_status()
            doc = r.json()
            doc.update(fields)
            w = s.put(self._u("/" + key), json=doc, timeout=60)
            if w.status_code in (201, 202):
                return
            if w.status_code != 409:  # 409 = konflik _rev -> ulangi
                w.raise_for_status()
        raise RuntimeError(f"update {key}: konflik _rev berulang")

    def insert(self, key, fields):
        r = self._s().put(self._u("/" + key), json=fields, timeout=60)
        r.raise_for_status()

    def scan(self, start_key, count):
        r = self._s().get(self._u("/_all_docs"),
                          params={"startkey": json.dumps(start_key), "limit": count,
                                  "include_docs": "true"}, timeout=120)
        r.raise_for_status()
        return [row["doc"] for row in r.json()["rows"]]

    def info(self):
        try:
            return {"server": "CouchDB " + self._s().get(self._base + "/", timeout=10).json()["version"]}
        except Exception as e:  # pragma: no cover
            return {"server": f"CouchDB (tidak terbaca: {e})"}

    def close(self):
        pass


# --------------------------------------------------------------------------- #
# Couchbase (SDK Python 4.x) -- EKSPERIMENTAL, belum diuji pada pembuatan repo ini
# --------------------------------------------------------------------------- #
class CouchbaseAdapter(DBAdapter):
    name = "couchbase"

    def __init__(self, host="127.0.0.1", user="Administrator", password="password",
                 bucket="ycsb", ram_quota_mb=1024, threads=8, **_):
        from datetime import timedelta
        from couchbase.auth import PasswordAuthenticator
        from couchbase.cluster import Cluster
        from couchbase.options import ClusterOptions
        self._cluster = Cluster(f"couchbase://{host}",
                                ClusterOptions(PasswordAuthenticator(user, password)))
        self._cluster.wait_until_ready(timedelta(seconds=30))
        self._bucket_name = bucket
        self._ram = ram_quota_mb
        self._bucket = None
        self._coll = None

    def prepare(self):
        import time
        from datetime import timedelta
        from couchbase.exceptions import BucketDoesNotExistException, BucketNotFoundException
        from couchbase.management.buckets import BucketType, CreateBucketSettings
        bm = self._cluster.buckets()
        try:
            bm.drop_bucket(self._bucket_name)
            time.sleep(3)
        except (BucketDoesNotExistException, BucketNotFoundException):
            pass
        bm.create_bucket(CreateBucketSettings(name=self._bucket_name, bucket_type=BucketType.COUCHBASE,
                                              ram_quota_mb=self._ram, flush_enabled=True,
                                              num_replicas=0))
        time.sleep(5)
        self._bucket = self._cluster.bucket(self._bucket_name)
        self._bucket.wait_until_ready(timedelta(seconds=30))
        self._coll = self._bucket.default_collection()
        self._cluster.query(f"CREATE PRIMARY INDEX ON `{self._bucket_name}`").execute()

    def load_batch(self, items):
        res = self._coll.upsert_multi({k: f for k, f in items})
        if not res.all_ok:
            raise RuntimeError("upsert_multi gagal sebagian")

    def read(self, key):
        from couchbase.exceptions import DocumentNotFoundException
        try:
            return self._coll.get(key).content_as[dict]
        except DocumentNotFoundException:
            return None

    def update(self, key, fields):
        import couchbase.subdocument as SD
        self._coll.mutate_in(key, [SD.upsert(k, v) for k, v in fields.items()])

    def insert(self, key, fields):
        self._coll.upsert(key, fields)

    def scan(self, start_key, count):
        from couchbase.options import QueryOptions
        q = (f"SELECT b.* FROM `{self._bucket_name}` b WHERE META(b).id >= $start "
             f"ORDER BY META(b).id LIMIT {int(count)}")
        return list(self._cluster.query(q, QueryOptions(named_parameters={"start": start_key})))

    def info(self):
        return {"server": "Couchbase Server (lihat UI untuk versi)"}


def make_adapter(name: str, threads: int, cfg: dict) -> DBAdapter:
    if name == "memory":
        return MemoryAdapter()
    if name == "mongodb":
        return MongoAdapter(uri=cfg["mongo_uri"], threads=threads)
    if name == "couchdb":
        return CouchDBAdapter(url=cfg["couchdb_url"], user=cfg["couchdb_user"],
                              password=cfg["couchdb_password"], threads=threads)
    if name == "couchbase":
        return CouchbaseAdapter(host=cfg["couchbase_host"], user=cfg["couchbase_user"],
                                password=cfg["couchbase_password"], threads=threads)
    raise ValueError(f"DB tidak dikenal: {name}")