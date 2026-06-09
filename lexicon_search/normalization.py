from __future__ import annotations

import re
import unicodedata


PUNCT_RE = re.compile(r"[-'’`´]+")
SPACE_RE = re.compile(r"\s+")


def normalize_query(value: str) -> str:
    return SPACE_RE.sub(" ", unicodedata.normalize("NFC", value).strip().casefold())


def accent_key(value: str) -> str:
    normalized = unicodedata.normalize("NFD", normalize_query(value))
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped)


def punctuation_key(value: str) -> str:
    replaced = PUNCT_RE.sub(" ", accent_key(value))
    return SPACE_RE.sub(" ", replaced).strip()
