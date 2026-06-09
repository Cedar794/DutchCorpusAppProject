from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import math
from typing import Iterator

from cc100_subtlex.core import dot_join, is_lowercase_token, normalize_word, subtlex_cd, subtlex_wf, zipf_frequency
from cc100_subtlex.frog import FrogToken


DOC_SENTINEL = "zzzzccdocboundaryzzzz"
ANNOTATED_BATCH_HEADER = "kind\tword\tpos\tlemma\tfreq\tlow_freq\tdoc_freq\tlow_doc_freq"


@dataclass
class AnnotatedCounter:
    total_documents: int = 0
    total_tokens: int = 0
    word_freq: Counter[str] = field(default_factory=Counter)
    word_low_freq: Counter[str] = field(default_factory=Counter)
    word_doc_freq: Counter[str] = field(default_factory=Counter)
    word_low_doc_freq: Counter[str] = field(default_factory=Counter)
    word_pos_freq: Counter[tuple[str, str]] = field(default_factory=Counter)
    word_pos_lemma_freq: Counter[tuple[str, str, str]] = field(default_factory=Counter)
    pos_lemma_freq: Counter[tuple[str, str]] = field(default_factory=Counter)
    _doc_words: set[str] = field(default_factory=set)
    _doc_low_words: set[str] = field(default_factory=set)
    _doc_had_token: bool = False

    def add_token(self, token: FrogToken) -> None:
        if token.word == DOC_SENTINEL:
            self.finish_document()
            return

        pos = token.pos_head
        if pos == "LET":
            return

        word = normalize_word(token.word)
        lemma = normalize_word(token.lemma)

        self.total_tokens += 1
        self.word_freq[word] += 1
        self.word_pos_freq[(word, pos)] += 1
        self.word_pos_lemma_freq[(word, pos, lemma)] += 1
        self.pos_lemma_freq[(pos, lemma)] += 1
        self._doc_words.add(word)
        self._doc_had_token = True

        if is_lowercase_token(token.word):
            self.word_low_freq[word] += 1
            self._doc_low_words.add(word)

    def finish_document(self) -> None:
        if not self._doc_had_token:
            self._doc_words.clear()
            self._doc_low_words.clear()
            return
        self.total_documents += 1
        self.word_doc_freq.update(self._doc_words)
        self.word_low_doc_freq.update(self._doc_low_words)
        self._doc_words.clear()
        self._doc_low_words.clear()
        self._doc_had_token = False


def _word_pos_items(counter: AnnotatedCounter, word: str) -> list[tuple[str, int]]:
    items = [
        (pos, freq)
        for (item_word, pos), freq in counter.word_pos_freq.items()
        if item_word == word
    ]
    return sorted(items, key=lambda item: (-item[1], item[0]))


def _dominant_lemma_for_pos(counter: AnnotatedCounter, word: str, pos: str) -> tuple[str, int]:
    candidates = [
        (lemma, freq)
        for (item_word, item_pos, lemma), freq in counter.word_pos_lemma_freq.items()
        if item_word == word and item_pos == pos
    ]
    if not candidates:
        return word, 0
    return sorted(candidates, key=lambda item: (-item[1], item[0]))[0]


def iter_subtlex_rows(counter: AnnotatedCounter) -> Iterator[dict[str, object]]:
    for word, freq in sorted(counter.word_freq.items(), key=lambda item: (-item[1], item[0])):
        pos_items = _word_pos_items(counter, word)
        pos_values = [pos for pos, _ in pos_items]
        pos_freqs = [pos_freq for _, pos_freq in pos_items]
        lemma_items = [_dominant_lemma_for_pos(counter, word, pos) for pos in pos_values]
        lemma_freqs = [
            counter.pos_lemma_freq[(pos, lemma)]
            for pos, (lemma, _word_pos_lemma_freq) in zip(pos_values, lemma_items)
        ]
        dominant_pos = pos_values[0] if pos_values else ""
        dominant_pos_freq = pos_freqs[0] if pos_freqs else 0
        dominant_lemma = lemma_items[0][0] if lemma_items else word
        dominant_lemma_freq = lemma_freqs[0] if lemma_freqs else 0

        yield {
            "Word": word,
            "FREQcount": freq,
            "CDcount": counter.word_doc_freq[word],
            "FREQlow": counter.word_low_freq[word],
            "CDlow": counter.word_low_doc_freq[word],
            "FREQlemma": sum(lemma_freqs),
            "SUBTLEXWF": subtlex_wf(freq, counter.total_tokens),
            "Zipf": zipf_frequency(freq, counter.total_tokens),
            "SUBTLEXCD": subtlex_cd(counter.word_doc_freq[word], counter.total_documents),
            "Lg10CD": math.log10(counter.word_doc_freq[word]),
            "dominant.pos": dominant_pos,
            "dominant.pos.freq": dominant_pos_freq,
            "dominant.pos.lemma": dominant_lemma,
            "dominant.pos.lemma.freq": dominant_lemma_freq,
            "all.pos": dot_join(pos_values),
            "all.pos.freq": dot_join(pos_freqs),
            "all.pos.lemma.freq": dot_join(lemma_freqs),
        }


def iter_annotated_count_rows(counter: AnnotatedCounter) -> Iterator[tuple[str, str, str, str, int, int, int, int]]:
    for word in sorted(counter.word_freq):
        yield (
            "word",
            word,
            "",
            "",
            counter.word_freq[word],
            counter.word_low_freq[word],
            counter.word_doc_freq[word],
            counter.word_low_doc_freq[word],
        )
    for (word, pos), freq in sorted(counter.word_pos_freq.items()):
        yield ("word_pos", word, pos, "", freq, 0, 0, 0)
    for (word, pos, lemma), freq in sorted(counter.word_pos_lemma_freq.items()):
        yield ("word_pos_lemma", word, pos, lemma, freq, 0, 0, 0)
    for (pos, lemma), freq in sorted(counter.pos_lemma_freq.items()):
        yield ("pos_lemma", "", pos, lemma, freq, 0, 0, 0)


def parse_annotated_count_row(line: str) -> tuple[str, str, str, str, int, int, int, int] | None:
    stripped = line.rstrip("\n")
    if not stripped or stripped == ANNOTATED_BATCH_HEADER:
        return None
    kind, word, pos, lemma, freq, low_freq, doc_freq, low_doc_freq = stripped.split("\t")
    return kind, word, pos, lemma, int(freq), int(low_freq), int(doc_freq), int(low_doc_freq)
