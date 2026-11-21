"""Minimal Okapi BM25 (the MVP corpus is a few hundred chunks, so in-memory is fine)."""

import math
from collections import Counter


class BM25:
    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.term_freqs = [Counter(doc) for doc in corpus]
        self.lengths = [len(doc) for doc in corpus]
        self.avg_len = (sum(self.lengths) / len(corpus)) if corpus else 0.0
        doc_freq: Counter[str] = Counter()
        for tf in self.term_freqs:
            doc_freq.update(tf.keys())
        n = len(corpus)
        self.idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in doc_freq.items()}

    def scores(self, query: list[str]) -> list[float]:
        terms = [t for t in set(query) if t in self.idf]
        out = []
        for tf, length in zip(self.term_freqs, self.lengths, strict=True):
            score = 0.0
            norm = self.k1 * (1 - self.b + self.b * length / self.avg_len) if self.avg_len else self.k1
            for term in terms:
                f = tf.get(term, 0)
                if f:
                    score += self.idf[term] * f * (self.k1 + 1) / (f + norm)
            out.append(score)
        return out
