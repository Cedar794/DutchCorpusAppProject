#!/usr/bin/env python3
"""Audit queue coverage, independent reviews, live translations and source repair history."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import asyncpg
try:
    from .complete_english_translations import counts, read_jsonl, validate_chunk, write_json
except ImportError:
    from complete_english_translations import counts, read_jsonl, validate_chunk, write_json


async def audit(root, require_finished=False):
    directories=sorted(p for p in (root/'chunks').iterdir() if p.is_dir())
    inputs=[row for p in directories for row in read_jsonl(p/'input.jsonl')]
    ids=[r['sense_id'] for r in inputs]
    assert len(ids)==len(set(ids)), 'Duplicate queue IDs'
    authored={}
    for directory in directories:
        if (directory/'output.jsonl').exists():
            source,output=validate_chunk(directory)
            authored[directory.name]={'count':len(source),'draft':sum(r['status']=='draft' for r in output),
                                      'blocked':sum(r['status']=='blocked' for r in output)}
    reviews={}
    for p in (root/'reviews').glob('*.json'):
        if p.name.startswith('repair-'):continue
        obj=json.loads(p.read_text())
        for name in obj.get('reviewed_chunks',[]):
            if name in reviews:raise ValueError('Duplicate primary review for '+name)
            reviews[name]=p.name
    receipts=[json.loads(p.read_text()) for p in (root/'batch-control').glob('*.done.json')]
    for receipt in receipts:
        assert receipt['author']!=receipt['reviewer'], 'Self-review receipt'
        path=root/'reviews'/receipt['review']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==receipt['review_sha256'], 'Changed reviewed report'
    for p in (root/'ready').glob('author-*.json'):
        obj=json.loads(p.read_text())
        for name in obj['chunks']:
            if name in reviews:
                assert obj['author']!=reviews[name].split('-')[1], 'Self-review ready group'
    c=await asyncpg.connect(os.environ.get('DATABASE_URL','postgresql://postgres:postgres@127.0.0.1:54322/postgres'))
    try:
        state=await counts(c)
        status=await c.fetch('''select s.id sense_id,l.lemma,p.pos,s.review_status,
          exists(select 1 from sense_translations t where t.sense_id=s.id and lang='en'
                 and t.review_status<>'rejected' and btrim(t.gloss)<>'') has_en,
          coalesce(nullif(s.display_definition_nl,''),s.definition_nl,'') definition_nl
          from senses s join lemmas l on l.id=s.lemma_id
          left join lemma_pos_entries p on p.id=s.lemma_pos_entry_id
          where s.id=any($1::bigint[]) order by s.id''',ids)
        unresolved=[dict(r) for r in status if r['review_status']!='rejected' and not r['has_en']]
        repairs=[dict(r) for r in await c.fetch('select action,count(*) actions,count(distinct sense_id) senses from english_source_repair_audit group by action order by action')]
        generated=await c.fetchrow('''select count(*) rows,
          count(*) filter(where t.review_status='needs_review') needs_review,
          count(*) filter(where t.review_status='rejected') superseded_or_withdrawn,
          count(*) filter(where right(t.gloss,5)<>'#aigc' or right(t.explanation,5)<>'#aigc') missing_marker
          from sense_translations t join sources src on src.id=t.source_id
          where t.lang='en' and src.source_key in ('aigc_subagent_english_v1','aigc_subagent_source_repair_v1')''')
        embeddings=await c.fetchval('select count(*) from sense_embeddings')
    finally:await c.close()
    result={'audited_at':datetime.now(timezone.utc).isoformat(),'queue_total':len(inputs),
      'total_chunks':len(directories),'authored_chunks':len(authored),
      'authored_rows':sum(r['count'] for r in authored.values()),
      'primary_reviewed_chunks':len(reviews),'primary_reviewed_rows':sum(len(read_jsonl(root/'chunks'/n/'input.jsonl')) for n in reviews),
      'new_imported_chunks':sum(len(r['chunks']) for r in receipts),
      'new_regular_imported_rows':sum(r['inserted'] for r in receipts),
      'queue_live_english':sum(r['review_status']!='rejected' and r['has_en'] for r in status),
      'queue_withdrawn_source_associations':sum(r['review_status']=='rejected' for r in status),
      'queue_unresolved':len(unresolved),'unresolved':unresolved,'database':state,
      'source_repairs':repairs,'generated_english':dict(generated),'embeddings':embeddings,
      'human_reviewed':False,'source_review_method':'independent_model_cross_review'}
    assert result['queue_live_english']+result['queue_withdrawn_source_associations']+result['queue_unresolved']==len(inputs)
    assert result['generated_english']['missing_marker']==0
    assert embeddings==0, 'Embedding was outside this task'
    if require_finished:
        assert result['authored_rows']==len(inputs), 'Unwritten queue rows'
        assert result['primary_reviewed_rows']==len(inputs), 'Unreviewed queue rows'
        assert result['new_imported_chunks']==len(directories)-12, 'Pending primary imports'
        assert state['missing_en_active']==0 and not unresolved, 'Unresolved active source senses remain'
    write_json(root/'completion-audit.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='unresolved'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',default='outputs/english_completion_20261022')
    p.add_argument('--require-finished',action='store_true')
    args=p.parse_args()
    asyncio.run(audit(Path(args.run_dir),args.require_finished))
