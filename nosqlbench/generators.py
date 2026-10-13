from __future__ import annotations

import random
import threading

import numpy as np

ZIPFIAN_CONSTANT = 0.99
SCRAMBLED_ITEM_COUNT = 10_000_000_000
SCRAMBLED_ZETAN = 26.46902820178302

_FNV_OFFSET_64 = 0xCBF29CE484222325
_FNV_PRIME_64 = 1099511628211
_MASK_64 = 0xFFFFFFFFFFFFFFFF

def fnv64(value: int) -> int:
    h = _FNV_OFFSET_64
    for _ in range(8):
        octet = value & 0xFF
        value >>= 8
        h ^= octet
        h = (h * _FNV_PRIME_64) & _MASK_64
    return h


def build_key(n: int) -> str:
    """Kunci dokumen 'user<hash>' (insertorder=hashed, bawaan YCSB)."""
    return "user" + str(fnv64(n))


_zeta_cache: dict[tuple[int, float], float] = {}
_zeta_lock = threading.Lock()


def zeta(n: int, theta: float) -> float:
    """Jumlah parsial deret zeta: sum_{i=1..n} 1/i^theta (di-cache)."""
    key = (n, theta)
    with _zeta_lock:
        if key in _zeta_cache:
            return _zeta_cache[key]
    total = 0.0
    chunk = 1_000_000
    start = 1
    while start <= n:
        stop = min(start + chunk, n + 1)
        i = np.arange(start, stop, dtype=np.float64)
        total += float(np.sum(1.0 / np.power(i, theta)))
        start = stop
    with _zeta_lock:
        _zeta_cache[key] = total
    return total


class Zipfian:
    """Pembangkit Zipfian atas [0, items) (item 0 paling sering)."""

    def __init__(self, items: int, theta: float = ZIPFIAN_CONSTANT,
                 zetan: float | None = None):
        if items < 2:
            raise ValueError("items minimal 2")
        self.items = items
        self.theta = theta
        self.zeta2 = zeta(2, theta)
        self.zetan = zetan if zetan is not None else zeta(items, theta)
        self.alpha = 1.0 / (1.0 - theta)
        self.eta = (1.0 - (2.0 / items) ** (1.0 - theta)) / (1.0 - self.zeta2 / self.zetan)
        self._half_pow = 0.5 ** theta

    def next(self, rng: random.Random) -> int:
        u = rng.random()
        uz = u * self.zetan
        if uz < 1.0:
            return 0
        if uz < 1.0 + self._half_pow:
            return 1
        v = int(self.items * (self.eta * u - self.eta + 1.0) ** self.alpha)
        return min(v, self.items - 1)


class UniformChooser:
    def __init__(self, n: int):
        self.n = n

    def next(self, rng: random.Random) -> int:
        return rng.randrange(self.n)


class ScrambledZipfianChooser:
    """Zipfian atas 10^10 item lalu di-hash ke [0, n) (YCSB 'zipfian')."""

    def __init__(self, n: int):
        self.n = n
        self._zipf = Zipfian(SCRAMBLED_ITEM_COUNT, ZIPFIAN_CONSTANT, SCRAMBLED_ZETAN)

    def next(self, rng: random.Random) -> int:
        return fnv64(self._zipf.next(rng)) % self.n


class AckCounter:
    """Penghitung kunci insert; `last()` hanya mencakup insert yang sudah selesai."""

    def __init__(self, start: int):
        self._next = start
        self._acked = start - 1
        self._done: set[int] = set()
        self._lock = threading.Lock()

    def next(self) -> int:
        with self._lock:
            v = self._next
            self._next += 1
            return v

    def acknowledge(self, v: int) -> None:
        with self._lock:
            self._done.add(v)
            while self._acked + 1 in self._done:
                self._acked += 1
                self._done.discard(self._acked)

    def last(self) -> int:
        with self._lock:
            return self._acked


class LatestChooser:
    """Distribusi 'latest': memilih kunci yang baru saja di-insert (YCSB workload D).

    Penyederhanaan: Zipfian dibangun sekali atas `basis` = jumlah record awal
    (YCSB memperbarui zeta secara inkremental saat jumlah record bertambah).
    """

    def __init__(self, basis: int, counter: AckCounter):
        self._zipf = Zipfian(max(basis, 2))
        self._counter = counter

    def next(self, rng: random.Random) -> int:
        return max(0, self._counter.last() - self._zipf.next(rng))


def make_chooser(name: str, n: int, counter: AckCounter | None = None):
    if name == "zipfian":
        return ScrambledZipfianChooser(n)
    if name == "uniform":
        return UniformChooser(n)
    if name == "latest":
        if counter is None:
            raise ValueError("distribusi 'latest' memerlukan counter")
        return LatestChooser(n, counter)
    raise ValueError(f"distribusi tidak dikenal: {name}")