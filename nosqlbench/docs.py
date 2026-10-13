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

    def fields(self, rng: random.Random) -> dict:
        i = rng.randrange(self.field_count)
        return {f"field{i}": self._pool[rng.randrange(len(self._pool))]}