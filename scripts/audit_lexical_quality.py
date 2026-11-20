#!/usr/bin/env python3
"""Audit a public-data snapshot; emit candidates, never mutate or merge senses."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lexicon_search.quality import EDITORIAL_NOTE, clean_marker, translation_signals


def audit(snapshot):
    senses = {s['sense_id']: s for s in snapshot['senses']}
    findings = []
    def add(rule, sid, **evidence):
        findings.append({'rule': rule, 'sense_id': sid, 'lemma': senses[sid]['lemma'],
                         'decision': 'needs_review', **evidence})
    for t in snapshot['translations']:
        for rule in translation_signals(t['lang'], t['gloss'], t['explanation']):
            if rule == 'grammar_only_gloss' and senses[t['sense_id']]['pos'] != 'VERB':
                continue  # absolute is a legitimate adjective, for example.
            add(rule, t['sense_id'], translation_id=t['id'], lang=t['lang'],
                gloss=t['gloss'], source_key=t['source_key'])
    groups = defaultdict(list)
    for s in senses.values():
        if EDITORIAL_NOTE.search(s['usage_note'] or ''):
            add('internal_usage_note', s['sense_id'], usage_note=s['usage_note'])
        definition = clean_marker(s['display_definition_nl'] or s['definition_nl'])
        normalized = re.sub(r'\s+', ' ', definition).casefold()
        if normalized:
            groups[(s['lemma_id'], s['pos'], s['domain'], s['register'], normalized)].append(s['sense_id'])
        if re.search(r'\b(?:zie betekenis|zie ook betekenis)\s*\d+', definition, re.I):
            add('unresolved_source_sense_reference', s['sense_id'], definition=definition)
    duplicate_groups = [ids for ids in groups.values() if len(ids) > 1]
    for ids in duplicate_groups:
        for sid in ids:
            add('same_definition_same_pos_candidate', sid, related_sense_ids=ids)
    for e in snapshot['examples']:
        if re.match(r'^\s*1\s*=', e['ex_nl']):
            add('example_template_prefix', e['sense_id'], example_id=e['id'], ex_nl=e['ex_nl'])
        if re.search(r'\bditctaor\b|\bte tegenspreken\b', e['ex_nl']):
            add('review_confirmed_example_typo', e['sense_id'], example_id=e['id'], ex_nl=e['ex_nl'])
    return {'scope': {'senses': len(senses), 'translations': len(snapshot['translations']),
                      'examples': len(snapshot['examples'])},
            'warning': 'Candidates are not confirmed errors. Do not extrapolate a sample error rate or auto-merge.',
            'rule_counts': dict(Counter(f['rule'] for f in findings)),
            'flagged_senses': len({f['sense_id'] for f in findings}),
            'duplicate_groups': duplicate_groups, 'findings': findings}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = audit(json.loads(args.snapshot.read_text()))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k not in {'findings','duplicate_groups'}}, ensure_ascii=False))
