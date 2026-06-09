from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ScoreBreakdown:
    score: float
    reasons: dict[str, float]


def edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + cost,
                )
            )
        previous = current
    return previous[-1]


def normalized_similarity(left: str, right: str) -> float:
    max_len = max(len(left), len(right), 1)
    return max(0.0, 1.0 - edit_distance(left, right) / max_len)


def _frequency_boost(frequency: int, weight: float) -> float:
    if frequency <= 0:
        return 0.0
    return min(math.log10(frequency + 1) / 6.0, 1.0) * weight


def _level_boost(level: int | None, weight: float) -> float:
    if level is None:
        return 0.0
    if level <= 1:
        return weight
    if level == 2:
        return weight * 0.7
    if level == 3:
        return weight * 0.35
    return 0.0


def dictionary_score(
    *,
    exact_match: bool,
    normalized_similarity_value: float,
    frequency: int,
    is_canonical: bool,
    level: int | None,
) -> ScoreBreakdown:
    reasons = {
        "exact_match": 1.0 if exact_match else 0.0,
        "normalized_similarity": max(0.0, min(normalized_similarity_value, 1.0)) * 0.4,
        "frequency_boost": _frequency_boost(frequency, 0.2),
        "canonical_boost": 0.1 if is_canonical else 0.0,
        "level_boost": _level_boost(level, 0.05),
    }
    return ScoreBreakdown(score=sum(reasons.values()), reasons=reasons)


def semantic_score(*, vector_similarity: float, frequency: int, level: int | None) -> ScoreBreakdown:
    reasons = {
        "semantic_score": max(0.0, min(vector_similarity, 1.0)),
        "frequency_boost": _frequency_boost(frequency, 0.08),
        "level_boost": _level_boost(level, 0.03),
    }
    return ScoreBreakdown(score=sum(reasons.values()), reasons=reasons)
