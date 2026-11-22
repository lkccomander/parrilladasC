"""Deterministic retrieval metrics; unknown labels are never converted into zero."""

import math
from collections.abc import Iterable, Sequence


def _ranked(values: Iterable[str], k: int) -> list[str]:
    if k < 1:
        raise ValueError("k must be positive")
    # Duplicate candidates occupy a rank but cannot earn credit twice.
    return list(values)[:k]


def recall_at_k(retrieved: Iterable[str], relevant: Iterable[str], k: int = 5):
    ranked, labels = _ranked(retrieved, k), set(relevant)
    return len(set(ranked) & labels) / len(labels) if labels else None


def precision_at_k(retrieved: Iterable[str], relevant: Iterable[str], k: int = 5):
    ranked, labels = _ranked(retrieved, k), set(relevant)
    return len(set(ranked) & labels) / k if labels else None


def reciprocal_rank(retrieved: Iterable[str], relevant: Iterable[str]):
    labels = set(relevant)
    if not labels:
        return None
    return next((1 / rank for rank, item in enumerate(retrieved, 1) if item in labels), 0.0)


def ndcg_at_k(retrieved: Iterable[str], relevant: Iterable[str], k: int = 5):
    ranked, labels = _ranked(retrieved, k), set(relevant)
    if not labels:
        return None
    seen = set()
    dcg = 0.0
    for rank, item in enumerate(ranked, 1):
        if item in labels and item not in seen:
            dcg += 1 / math.log2(rank + 1)
        seen.add(item)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(labels)) + 1))
    return dcg / ideal


def measured_mean(values: Iterable[float | None]) -> float | None:
    measured = [value for value in values if value is not None]
    return sum(measured) / len(measured) if measured else None


def percentile(values: Sequence[float], quantile: float) -> float | None:
    """Linear interpolation matching PostgreSQL percentile_cont."""
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must lie in [0, 1]")
    if not values:
        return None
    ordered = sorted(values)
    if not all(math.isfinite(value) for value in ordered):
        raise ValueError("values must be finite")
    index = (len(ordered) - 1) * quantile
    lower, upper = math.floor(index), math.ceil(index)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def citation_accuracy(selected: Iterable[str], retrieved: Iterable[str]) -> float | None:
    selected = list(selected)
    allowed = set(retrieved)
    if not selected:
        return None
    return len(set(selected) & allowed) / len(selected)


def grounded_text_proxy(answer: str, selected_texts: Sequence[str]) -> float | None:
    """Only verifies exact stored-fact rendering; not semantic faithfulness."""
    if not selected_texts:
        return None
    return float(answer == "\n\n".join(selected_texts))
