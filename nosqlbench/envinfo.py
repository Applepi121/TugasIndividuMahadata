from __future__ import annotations

import os
import platform
import sys
from importlib import metadata

def _mem_gb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return round(int(line.split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    try:
        import psutil
        return round(psutil.virtual_memory().total / 1024 ** 3, 1)
    except Exception:  # noqa: BLE001
        return None


def collect(db_infos: dict | None = None) -> dict:
    pk = {}
    for p in ("pymongo", "requests", "numpy", "pandas", "matplotlib", "couchbase"):
        try:
            pk[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            pass
    return {"python": sys.version.split()[0], "platform": platform.platform(),
            "machine": platform.machine(), "processor": platform.processor(),
            "cpu_logical": os.cpu_count(), "ram_gb": _mem_gb(),
            "packages": pk, "databases": db_infos or {}}