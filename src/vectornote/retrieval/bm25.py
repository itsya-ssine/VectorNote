"""BM25 keyword search, implemented from scratch (no extra dependency).

Complements vector search: exact terms, acronyms, identifiers and rare words
that an embedding model may blur are matched literally here.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Sequence

from vectornote.models import Chunk

_TOKEN = re.compile(r"\w+")

# Small English + French stop list. "c" is deliberately kept (the language).
_STOPWORDS = frozenset(
    """
    a an and are as at be by for from has have in is it its of on or that the to was were
    will with this these those not no but if then than so such into about which who what
    when where how why can could should would may might do does did their there them they
    you your we our he she his her i me my
    le la les un une des du de d l et ou en au aux ce ces cet cette est sont ont avec pour
    par sur dans que qui quoi dont ne pas plus se sa son ses leur leurs nous vous ils elles
    il elle je tu mon ma mes ton ta tes s n j m t qu
    """.split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase, strip accents (so 'réseau' matches 'reseau'), drop stop words."""
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return [token for token in _TOKEN.findall(folded) if token not in _STOPWORDS]


class Bm25Index:
    """In-memory Okapi BM25 over a list of chunks (Lucene-style, always-positive IDF)."""

    def __init__(self, chunks: Sequence[Chunk], k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._chunks = sorted(chunks, key=lambda c: c.chunk_id)
        self._position = {chunk.chunk_id: i for i, chunk in enumerate(self._chunks)}
        self._lengths: list[int] = []
        self._term_freqs: list[Counter[str]] = []
        self._postings: dict[str, list[int]] = defaultdict(list)
        for i, chunk in enumerate(self._chunks):
            counts = Counter(tokenize(chunk.text))
            self._term_freqs.append(counts)
            self._lengths.append(sum(counts.values()))
            for term in counts:
                self._postings[term].append(i)
        n = len(self._chunks)
        self._avg_length = sum(self._lengths) / n if n else 0.0

    def __len__(self) -> int:
        return len(self._chunks)

    def _idf(self, doc_frequency: int) -> float:
        n = len(self._chunks)
        return math.log(1.0 + (n - doc_frequency + 0.5) / (doc_frequency + 0.5))

    def _term_score(self, term: str, doc: int) -> float:
        tf = self._term_freqs[doc][term]
        if tf == 0:
            return 0.0
        length_norm = 1.0 - self._b
        if self._avg_length:
            length_norm += self._b * self._lengths[doc] / self._avg_length
        saturation = tf * (self._k1 + 1.0) / (tf + self._k1 * length_norm)
        return self._idf(len(self._postings[term])) * saturation

    def search(
        self, query: str, k: int, sources: Sequence[str] | None = None
    ) -> list[tuple[Chunk, float]]:
        """Top `k` chunks containing at least one query term, best first."""
        allowed = set(sources) if sources else None
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokenize(query)):
            for doc in self._postings.get(term, ()):
                if allowed is not None and self._chunks[doc].source not in allowed:
                    continue
                scores[doc] += self._term_score(term, doc)
        ranked = sorted(scores.items(), key=lambda item: (-item[1], self._chunks[item[0]].chunk_id))
        return [(self._chunks[doc], score) for doc, score in ranked[:k]]

    def score(self, query: str, chunk_id: str) -> float:
        """BM25 score of one specific chunk for `query` (0.0 if unknown or no match)."""
        doc = self._position.get(chunk_id)
        if doc is None:
            return 0.0
        return sum(self._term_score(term, doc) for term in set(tokenize(query)))
