from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrogToken:
    index: int
    word: str
    lemma: str
    morphology: str
    pos: str
    confidence: float | None
    ner: str | None
    chunk: str | None
    parse_index: int | None
    parse_role: str | None

    @property
    def pos_head(self) -> str:
        return pos_head(self.pos)


def pos_head(pos: str) -> str:
    return pos.split("(", 1)[0]


def parse_frog_line(line: str) -> FrogToken | None:
    stripped = line.strip()
    if not stripped:
        return None

    parts = stripped.split("\t")
    if len(parts) < 5:
        parts = stripped.split(maxsplit=9)
    if len(parts) < 5:
        raise ValueError(f"Expected at least 5 Frog columns, got {len(parts)}: {line!r}")

    confidence = None
    if len(parts) > 5:
        try:
            confidence = float(parts[5])
        except ValueError:
            confidence = None

    parse_index = None
    if len(parts) > 8:
        try:
            parse_index = int(parts[8])
        except ValueError:
            parse_index = None

    return FrogToken(
        index=int(parts[0]),
        word=parts[1],
        lemma=parts[2],
        morphology=parts[3],
        pos=parts[4],
        confidence=confidence,
        ner=parts[6] if len(parts) > 6 else None,
        chunk=parts[7] if len(parts) > 7 else None,
        parse_index=parse_index,
        parse_role=parts[9] if len(parts) > 9 else None,
    )

