#!/usr/bin/env python3
"""Import completed, independently reviewed English batches, one transaction at a time."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from complete_english_translations import read_jsonl, validate_chunk, write_json

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',default='outputs/english_completion_20261022')
    args=parser.parse_args()
    run_dir=Path(args.run_dir).resolve()
    control=run_dir/'batch-control';control.mkdir(exist_ok=True)
    backup=run_dir/'after-english-import.dump'
    summary=[]
    for path in sorted((run_dir/'reviews').glob('review-*.json')):
        done=control/(path.stem+'.done.json')
        if done.exists(): continue
        try: review=json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError: continue  # Writer has not published full JSON yet.
        chunks=review['reviewed_chunks']
        if not chunks or len(chunks)!=len(set(chunks)): raise ValueError('Invalid review coverage')
        ready=[]
        for candidate in (run_dir/'ready').glob('author-*.json'):
            try: obj=json.loads(candidate.read_text(encoding='utf-8'))
            except json.JSONDecodeError: continue
            if set(obj['chunks'])==set(chunks): ready.append(obj)
        if len(ready)!=1: continue
        writer=ready[0]['author']; reviewer=path.name.split('-')[1]
        if writer==reviewer: raise ValueError('Self-review is not permitted')
        count=sum(len(validate_chunk(run_dir/'chunks'/n)[0]) for n in chunks)
        if count!=ready[0]['count'] or count!=review['reviewed_count']:
            raise ValueError('Batch row count does not match declared review coverage')
        log=control/(path.stem+'.log')
        with log.open('a',encoding='utf-8') as handle:
            base=[sys.executable,str(ROOT/'scripts/complete_english_translations.py')]
            common=['--run-dir',str(run_dir),'--chunks',','.join(chunks)]
            subprocess.run(base+['apply-reviews',*common,'--reviews',path.name],cwd=ROOT,
                           stdout=handle,stderr=subprocess.STDOUT,check=True)
            manifest=run_dir/'review-application.json'
            archived=control/(path.stem+'.applied.json')
            archived.write_bytes(manifest.read_bytes())
            before_imports=set((run_dir/'imports').glob('*.json'))
            subprocess.run(base+['import',*common,'--backup',str(backup)],cwd=ROOT,
                           stdout=handle,stderr=subprocess.STDOUT,check=True)
        reports=set((run_dir/'imports').glob('*.json'))-before_imports
        if len(reports)!=1: raise RuntimeError('Expected one import report')
        report_path=reports.pop();report=json.loads(report_path.read_text())
        state={'finished_at':datetime.now(timezone.utc).isoformat(),'review':path.name,
               'review_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
               'chunks':chunks,'selected':count,'inserted':report['imported_count'],
               'blocked':report['blocked_count'],'after':report['after'],
               'report':str(report_path),'author':writer,'reviewer':reviewer}
        write_json(done,state);summary.append(state)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
