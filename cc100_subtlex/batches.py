from __future__ import annotations


def parse_count_row(line: str) -> tuple[str, int, int, int, int] | None:
    stripped = line.rstrip("\n")
    if not stripped or stripped == "word\tfreq\tlow_freq\tdoc_freq\tlow_doc_freq":
        return None
    word, freq, low_freq, doc_freq, low_doc_freq = stripped.split("\t")
    return word, int(freq), int(low_freq), int(doc_freq), int(low_doc_freq)
