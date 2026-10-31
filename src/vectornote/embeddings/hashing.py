"""Dependency-free bag-of-words embedder for tests, CI and offline smoke runs.

It hashes words into a fixed-size vector, so texts that share words are close in
cosine similarity. It has no semantic understanding: use the real encoder for
actual retrieval quality.
"""

from __future__ import annotations

import math
import re
import zlib
from collections import Counter
from collections.abc import Sequence

_TOKEN = re.compile(r"\w+")


class HashingEmbedder:
    def __init__(self, dimension: int = 384) -> None:
        self.name = "hashing"
        self.dimension = dimension

    def _encode_one(self, text: str) -> list[float]:
        counts = Counter(_TOKEN.findall(text.lower()))
        vector = [0.0] * self.dimension
        for token, count in counts.items():
            index = zlib.crc32(token.encode("utf-8")) % self.dimension
            vector[index] += 1.0 + math.log(count)
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            vector[0] = 1.0
            return vector
        return [v / norm for v in vector]

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._encode_one(text) for text in texts]
