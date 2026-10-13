from __future__ import annotations

import random
import string

from .workloads import FIELD_COUNT, FIELD_LENGTH

class DocFactory:
    def __init__(self, field_count: int = FIELD_COUNT, field_length: int = FIELD_LENGTH, pool_size: int = 2048, seed: int = 42):
        rng = random.Random(seed)
        alphabet = string.ascii_letters + string.digits
        self.field_count = field_count
        self._pool = ["".join(rng.choices(alphabet, k=field_length)) for _ in range(pool_size)]

    def document(self, rng: random.Random) -> dict:
        """Mengembalikan dokumen lengkap berisi 20 field (10 KB) untuk load/insert."""
        return {f"field{i}": self._pool[rng.randrange(len(self._pool))] for i in range(self.field_count)}

    def fields(self, rng: random.Random) -> dict:
        """Mengembalikan 1 field acak."""
        i = rng.randrange(self.field_count)
        return {f"field{i}": self._pool[rng.randrange(len(self._pool))]}

    def one_field(self, arg1: random.Random | str | None = None, field_name: str = "field0") -> dict:
        """Mengembalikan 1 field update secara fleksibel baik dipanggil one_field(rng) maupun one_field('field0')."""
        rng = None
        if isinstance(arg1, str):
            field_name = arg1
        elif hasattr(arg1, 'randrange') or hasattr(arg1, 'choice'):
            rng = arg1

        if rng is not None:
            i = rng.randrange(self.field_count)
            val = self._pool[rng.randrange(len(self._pool))]
            fname = f"field{i}"
        else:
            val = random.choice(self._pool)
            fname = field_name if isinstance(field_name, str) else "field0"

        return {fname: val}