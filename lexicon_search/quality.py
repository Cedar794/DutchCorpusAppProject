"""Conservative lexical quality signals; warnings are not automatic corrections."""
from __future__ import annotations

import re


EDITORIAL_NOTE = re.compile(
    r"\bdetach\b.*\b(?:synset|association)\b|"
    r"\b(?:source repair|superseded translations|cross-reviewed|human-approved)\b",
    re.I,
)
FORMAT_RESIDUE = re.compile(r"\{\\(?:fn|fs|an|pos|bord)|<\/?(?:span|div|br)\b|\{\{[^}]+\}\}", re.I)
GRAMMAR_ONLY = re.compile(
    r"^(?:及物(?:动词|的)?|不及物(?:动词|的)?|情态动词|作格|作格动词|绝对|传递性(?:的)?|"
    r"transitive(?: verb)?|intransitive(?: verb)?|ergative(?: verb)?|absolutel?y?)$", re.I
)
DUTCH_PHRASE = re.compile(
    r"\b(?:iemand|iets|zich|zeer|voorwerp|onhandig|omvatten|gebruikt|"
    r"ergatief|overgankelijk|onovergankelijk)\b", re.I
)


def clean_marker(text: str | None) -> str:
    return (text or "").removesuffix("#aigc").strip()


def translation_signals(lang: str, gloss: str, explanation: str = "") -> list[str]:
    """Return review candidates, preserving legitimate grammar and loanword uses."""
    gloss = clean_marker(gloss)
    text = gloss + " " + clean_marker(explanation)
    findings = []
    if FORMAT_RESIDUE.search(text):
        findings.append("format_residue")
    if EDITORIAL_NOTE.search(text):
        findings.append("editorial_note")
    if GRAMMAR_ONLY.fullmatch(gloss):
        findings.append("grammar_only_gloss")
    if lang == "zh" and not re.search(r"[\u3400-\u9fff]", gloss) and not re.fullmatch(r'[\d\s“”".,%+-]+', gloss):
        findings.append("chinese_gloss_without_han")
    if lang == "en" and re.search(r"[\u3400-\u9fff]", gloss):
        findings.append("english_gloss_contains_han")
    if DUTCH_PHRASE.search(gloss):
        findings.append("possible_untranslated_dutch")
    # Word count alone never proves truncation; these endings only request review.
    if lang == "en" and re.search(r"\b(?:a|an|the|of|with|and|or|to|for|by)\s*$", gloss, re.I):
        findings.append("possible_incomplete_gloss")
    if any(gloss.count(left) != gloss.count(right) for left, right in (("(", ")"), ("（", "）"), ("[", "]"))):
        findings.append("unbalanced_gloss_delimiters")
    return findings


def translation_blockers(lang: str, gloss: str, explanation: str = "") -> list[str]:
    """Only definite presentation corruption blocks import; semantics need review."""
    return [x for x in translation_signals(lang, gloss, explanation)
            if x in {"format_residue", "editorial_note"}]
