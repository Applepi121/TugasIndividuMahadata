from __future__ import annotations

import random
from dataclasses import dataclass

FIELD_COUNT = 20
FIELD_LENGTH = 500
MAX_SCAN_LENGTH = 100

READ, UPDATE, INSERT, SCAN, RMW = "READ", "UPDATE", "INSERT", "SCAN", "RMW"

@dataclass(frozen=True)
class Workload:
    name: str
    title: str
    proportions: dict
    request_distribution: str

@property
def has_inserts(self) -> bool:
    return self.proportions.get(INSERT, 0) > 0

def chooser(self):
    """Mengembalikan fungsi rng -> nama operasi sesuai proporsi yang ditentukan."""
    ops, cum, acc = [], [], 0.0
    for op, p in self.proportions.items():
        acc += p
        ops.append(op)
        cum.append(acc)

    def choose(rng: random.Random) -> str:
        r = rng.random() * acc
        for op, c in zip(ops, cum):
            if r < c:
                return op
        return ops[-1]

    return choose

WORKLOADS: dict[str, Workload] = {
    "A": Workload("A", "Update Heavy", {READ: 0.5, UPDATE: 0.5}, "zipfian"),
    "B": Workload("B", "Read Mostly", {READ: 0.95, UPDATE: 0.05}, "zipfian"),
    "C": Workload("C", "Read Only", {READ: 1.0}, "zipfian"),
    "D": Workload("D", "Read Latest", {READ: 0.95, INSERT: 0.05}, "latest"),
    "E": Workload("E", "Short Ranges", {SCAN: 0.95, INSERT: 0.05}, "zipfian"),
    "F": Workload("F", "Read Modify Write", {READ: 0.5, RMW: 0.5}, "zipfian"),
    "G": Workload("G", "Update Mostly", {UPDATE: 0.95, READ: 0.05}, "zipfian"),
    "H": Workload("H", "Update Only", {UPDATE: 1.0}, "zipfian"),
} 

# Urutan eksekusi: workload tanpa insert dulu agar data muat ulang seminimal mungkin.
EXECUTION_ORDER = ["H", "G", "F", "C", "B", "A", "D", "E"]