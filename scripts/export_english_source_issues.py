#!/usr/bin/env python3
"""Build an evidence pack for unresolved source senses; never invent translations."""
import argparse
import json
from pathlib import Path

from complete_english_translations import read_jsonl, write_json, write_jsonl


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',default='outputs/english_completion_20261022')
    parser.add_argument('--include-provisional',action='store_true')
    args=parser.parse_args()
    root=Path(args.run_dir)
    wn_path=root/'source-evidence/wordnet-evidence.jsonl'
    wn={r['sense_id']:r for r in read_jsonl(wn_path)} if wn_path.exists() else {}
    raw_path=root/'source-evidence/database-source-snapshots.jsonl'
    raw={r['sense_id']:r for r in read_jsonl(raw_path)} if raw_path.exists() else {}
    reviewed={f'{n:04d}' for n in range(1,13)}
    for p in (root/'batch-control').glob('*.done.json'):
        reviewed.update(json.loads(p.read_text())['chunks'])
    rows=[]
    for directory in sorted((root/'chunks').iterdir()):
        if not directory.is_dir() or not (directory/'output.jsonl').exists():continue
        if directory.name not in reviewed and not args.include_provisional:continue
        try:outputs=read_jsonl(directory/'output.jsonl')
        except json.JSONDecodeError:continue
        inputs={r['sense_id']:r for r in read_jsonl(directory/'input.jsonl')}
        for row in outputs:
            if row['status']!='blocked':continue
            sid=row['sense_id']
            snapshot=raw.get(sid)
            if snapshot and isinstance(snapshot.get('raw_payload'),str):
                snapshot={**snapshot,'raw_payload':json.loads(snapshot['raw_payload'])}
            rows.append({'chunk':directory.name,'cross_reviewed':directory.name in reviewed,
                         'input':inputs[sid],'decision':row,'wordnet':wn.get(sid),
                         'original_source':snapshot})
    target=root/'source-issues';target.mkdir(exist_ok=True)
    write_jsonl(target/'evidence.jsonl',rows)
    write_json(target/'summary.json',{'count':len(rows),'cross_reviewed':sum(r['cross_reviewed'] for r in rows),
                  'with_wordnet_evidence':sum(r['wordnet'] is not None for r in rows),
                  'status':'requires_source_disambiguation','human_reviewed':False})
    print(len(rows))


if __name__=='__main__':main()
