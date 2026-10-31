"""The interface every embedding backend implements."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Embedder(Protocol):
    """Turns texts into fixed-size vectors. Vectors are L2-normalized."""

    name: str

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...
