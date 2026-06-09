from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import re
import unicodedata
from typing import Iterable, Iterator, Sequence


WORD_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)


@dataclass
class TokenCountResult:
    total_documents: int
    total_tokens: int
    word_freq: Counter[str]
    word_low_freq: Counter[str]
    word_doc_freq: Counter[str]
    word_low_doc_freq: Counter[str]


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def iter_word_tokens(text: str) -> Iterator[str]:
    normalized = normalize_text(text)
    for match in WORD_RE.finditer(normalized):
        yield match.group(0)


def normalize_word(token: str) -> str:
    return normalize_text(token).casefold()


def is_lowercase_token(token: str) -> bool:
    normalized = normalize_text(token)
    return normalized == normalized.casefold()


def subtlex_wf(freq_count: int, total_tokens: int) -> float:
    if total_tokens <= 0:
        raise ValueError("total_tokens must be positive")
    return freq_count / total_tokens * 1_000_000


def zipf_frequency(freq_count: int, total_tokens: int) -> float:
    if freq_count <= 0:
        raise ValueError("freq_count must be positive")
    if total_tokens <= 0:
        raise ValueError("total_tokens must be positive")
    return math.log10(freq_count / total_tokens * 1_000_000_000)


def subtlex_cd(cd_count: int, total_documents: int) -> float:
    if total_documents <= 0:
        raise ValueError("total_documents must be positive")
    return cd_count / total_documents * 100


def dot_join(values: Sequence[object]) -> str:
    return "." + ".".join(str(value) for value in values) + "."


def count_token_lines(lines: Iterable[str]) -> TokenCountResult:
    word_freq: Counter[str] = Counter()
    word_low_freq: Counter[str] = Counter()
    word_doc_freq: Counter[str] = Counter()
    word_low_doc_freq: Counter[str] = Counter()
    total_documents = 0
    total_tokens = 0

    for line in lines:
        tokens_in_doc: set[str] = set()
        low_tokens_in_doc: set[str] = set()
        doc_had_token = False

        for token in iter_word_tokens(line):
            doc_had_token = True
            word = normalize_word(token)
            total_tokens += 1
            word_freq[word] += 1
            tokens_in_doc.add(word)

            if is_lowercase_token(token):
                word_low_freq[word] += 1
                low_tokens_in_doc.add(word)

        if doc_had_token:
            total_documents += 1
            word_doc_freq.update(tokens_in_doc)
            word_low_doc_freq.update(low_tokens_in_doc)

    return TokenCountResult(
        total_documents=total_documents,
        total_tokens=total_tokens,
        word_freq=word_freq,
        word_low_freq=word_low_freq,
        word_doc_freq=word_doc_freq,
        word_low_doc_freq=word_low_doc_freq,
    )


def count_rows(result: TokenCountResult) -> Iterator[tuple[str, int, int, int, int]]:
    for word in sorted(result.word_freq):
        yield (
            word,
            result.word_freq[word],
            result.word_low_freq[word],
            result.word_doc_freq[word],
            result.word_low_doc_freq[word],
        )
