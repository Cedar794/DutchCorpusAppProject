from __future__ import annotations

from collections import defaultdict

from lexicon_search.models import FormSummary, LemmaSummary, LookupCandidate
from lexicon_search.normalization import accent_key, normalize_query, punctuation_key
from lexicon_search.scoring import dictionary_score, normalized_similarity


class DictionaryIndex:
    def __init__(
        self,
        lemmas_by_norm: dict[str, LemmaSummary],
        forms_by_norm: dict[str, list[FormSummary]],
        accent_entries: dict[str, list[LookupCandidate]],
        prefix_entries: dict[str, list[LookupCandidate]],
    ) -> None:
        self.lemmas_by_norm = lemmas_by_norm
        self.forms_by_norm = forms_by_norm
        self.accent_entries = accent_entries
        self.prefix_entries = prefix_entries

    @classmethod
    def from_rows(cls, lemmas: list[LemmaSummary], forms: list[FormSummary]) -> "DictionaryIndex":
        lemmas_by_norm = {lemma.lemma_norm: lemma for lemma in lemmas}
        forms_by_norm: dict[str, list[FormSummary]] = defaultdict(list)
        accent_entries: dict[str, list[LookupCandidate]] = defaultdict(list)
        prefix_entries: dict[str, list[LookupCandidate]] = defaultdict(list)

        for form in forms:
            forms_by_norm[form.form_norm].append(form)
            candidate = _candidate_from_form(form, form.form_norm, "form_exact")
            accent_entries[accent_key(form.form_norm)].append(candidate)
            accent_entries[punctuation_key(form.form_norm)].append(candidate)
            for prefix in _prefixes(form.form_norm):
                prefix_entries[prefix].append(candidate)

        for lemma in lemmas:
            candidate = _candidate_from_lemma(lemma, "lemma_exact")
            accent_entries[accent_key(lemma.lemma_norm)].append(candidate)
            accent_entries[punctuation_key(lemma.lemma_norm)].append(candidate)
            for prefix in _prefixes(lemma.lemma_norm):
                prefix_entries[prefix].append(candidate)

        for entries in prefix_entries.values():
            entries.sort(key=lambda item: (-item.score, item.lemma.lemma))

        return cls(dict(lemmas_by_norm), dict(forms_by_norm), dict(accent_entries), dict(prefix_entries))

    def lookup(self, query: str, limit: int = 5) -> list[LookupCandidate]:
        normalized = normalize_query(query)
        candidates: list[LookupCandidate] = []

        for form in self.forms_by_norm.get(normalized, []):
            candidates.append(_candidate_from_form(form, normalized, "form_exact"))

        lemma = self.lemmas_by_norm.get(normalized)
        if lemma is not None:
            candidates.append(_candidate_from_lemma(lemma, "lemma_exact"))

        if not candidates:
            candidates.extend(self.accent_entries.get(accent_key(normalized), []))

        if not candidates:
            candidates.extend(self.accent_entries.get(punctuation_key(normalized), []))

        return _dedupe_candidates(candidates)[:limit]

    def suggest(self, query: str, limit: int = 10) -> list[LookupCandidate]:
        normalized = normalize_query(query)
        candidates = self.prefix_entries.get(normalized, [])
        return _dedupe_candidates(candidates)[:limit]


def _prefixes(value: str) -> list[str]:
    return [value[:index] for index in range(1, min(len(value), 20) + 1)]


def _candidate_from_form(form: FormSummary, query: str, match_type: str) -> LookupCandidate:
    breakdown = dictionary_score(
        exact_match=form.form_norm == query,
        normalized_similarity_value=normalized_similarity(query, form.form_norm),
        frequency=form.frequency or form.lemma.frequency,
        is_canonical=form.is_canonical,
        level=form.lemma.level,
    )
    return LookupCandidate(
        lemma=form.lemma,
        form_id=form.form_id,
        form=form.form,
        match_type=match_type,
        score=breakdown.score,
        confidence=min(breakdown.score, 1.0),
    )


def _candidate_from_lemma(lemma: LemmaSummary, match_type: str) -> LookupCandidate:
    breakdown = dictionary_score(
        exact_match=True,
        normalized_similarity_value=1.0,
        frequency=lemma.frequency,
        is_canonical=True,
        level=lemma.level,
    )
    return LookupCandidate(
        lemma=lemma,
        form_id=None,
        form=None,
        match_type=match_type,
        score=breakdown.score,
        confidence=min(breakdown.score, 1.0),
    )


def _dedupe_candidates(candidates: list[LookupCandidate]) -> list[LookupCandidate]:
    best: dict[int, LookupCandidate] = {}
    for candidate in candidates:
        existing = best.get(candidate.lemma.lemma_id)
        if existing is None or candidate.score > existing.score:
            best[candidate.lemma.lemma_id] = candidate
    return sorted(best.values(), key=lambda item: (-item.score, item.lemma.lemma))
