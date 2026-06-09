from __future__ import annotations

from lexicon_search.models import RelatedResult


RELATION_PRIORITY = {
    "synonym": 1.0,
    "antonym": 0.9,
    "family": 0.8,
    "word_family": 0.8,
    "related": 0.6,
}


def rank_related_results(
    related: list[RelatedResult],
    *,
    primary_lemma_ids: list[int],
    limit: int,
) -> list[RelatedResult]:
    primary = set(primary_lemma_ids)
    best: dict[int, RelatedResult] = {}
    for item in related:
        if item.lemma_id in primary:
            continue
        existing = best.get(item.lemma_id)
        if existing is None or _sort_score(item) > _sort_score(existing):
            best[item.lemma_id] = item
    return sorted(best.values(), key=lambda item: (-_sort_score(item), item.lemma))[:limit]


def _sort_score(item: RelatedResult) -> float:
    relation_weight = RELATION_PRIORITY.get(item.relation_type, 0.5)
    return relation_weight + item.score * 0.2
