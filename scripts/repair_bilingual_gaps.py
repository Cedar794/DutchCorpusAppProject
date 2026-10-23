#!/usr/bin/env python3
"""Validate independently authored lexical repairs and commit one reviewed chunk atomically."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import asyncpg

ROOT=Path(__file__).resolve().parents[1]
SOURCE='aigc_bilingual_gap_repair_v1'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def marked(value):
    return isinstance(value,str) and value.endswith('#aigc') and bool(value[:-5].strip())


def validate_row(row,source):
    if type(row.get('sense_id')) is not int or row['sense_id']!=source['sense_id']:
        raise ValueError('Changed sense ID')
    if row.get('snapshot_hash')!=source['snapshot_hash']:
        raise ValueError('Changed snapshot hash')
    if row.get('decision') not in {'correct','keep','blocked'}:
        raise ValueError('Unknown decision')
    if type(row.get('confidence')) not in (int,float) or not 0<=row['confidence']<=.9:
        raise ValueError('Confidence outside 0..0.9')
    if not marked(row.get('reason')):
        raise ValueError('Unmarked decision reason')
    if row['decision']=='correct':
        translations=row.get('translations')
        if not isinstance(translations,dict) or set(translations)!={'en','zh'}:
            raise ValueError('Correction requires both languages')
        for lang in ['en','zh']:
            pair=translations[lang]
            if not isinstance(pair,dict) or any(not marked(pair.get(k)) for k in ['gloss','explanation']):
                raise ValueError('Empty or unmarked translation')
        if not any('\u3400'<=c<='\u9fff' for c in translations['zh']['gloss']):
            raise ValueError('Chinese gloss needs a Chinese explanation of the form')
    elif row.get('translations') is not None:
        raise ValueError('Non-correction cannot contain hidden translations')


def prepare(root,job):
    name=job['chunk'];path=root/'chunks'/name
    inputs=rows(path/'input.jsonl');output=rows(path/'output.jsonl')
    if len(inputs)!=job['count'] or len(output)!=len(inputs):raise ValueError('Missing output rows')
    if len({x['sense_id'] for x in inputs})!=len(inputs):raise ValueError('Duplicate input IDs')
    for row,source in zip(output,inputs):validate_row(row,source)
    ready=json.loads((root/'ready'/f"author-{job['author']}-{name}.json").read_text())
    sha=hashlib.sha256((path/'output.jsonl').read_bytes()).hexdigest()
    if ready['author']!=job['author'] or ready['chunk']!=name or ready['count']!=len(inputs) or ready['output_sha256']!=sha:
        raise ValueError('Invalid ready fingerprint')
    reviewpath=root/'reviews'/f"review-{job['reviewer']}-{name}.json"
    review=json.loads(reviewpath.read_text())
    if job['author']==job['reviewer'] or review['author']!=job['author'] or review['reviewer']!=job['reviewer']:
        raise ValueError('Review must be independent')
    if review['chunk']!=name or review['output_sha256']!=sha or review['reviewed_count']!=len(inputs):
        raise ValueError('Wrong reviewed snapshot')
    decisions=review['decisions']
    if len(decisions)!=len(inputs) or {x['sense_id'] for x in decisions}!={x['sense_id'] for x in inputs}:
        raise ValueError('Incomplete independent review')
    byid={x['sense_id']:x for x in decisions};final=[]
    for source,row in zip(inputs,output):
        decision=byid[source['sense_id']]
        if not marked(decision.get('reason')):raise ValueError('Unmarked review reason')
        if decision['verdict']=='replace':
            row=decision['replacement'];validate_row(row,source)
        elif decision['verdict']!='approve':raise ValueError('Unknown review verdict')
        final.append(row)
    return final,{'author':job['author'],'reviewer':job['reviewer'],'chunk':name,'output_sha256':sha,
                  'review_sha256':hashlib.sha256(reviewpath.read_bytes()).hexdigest(),
                  'review_file':str(reviewpath),'human_reviewed':False}


async def apply(connection,root,job,final,provenance):
    snapshots={x['sense_id']:x for x in rows(root/'chunks'/job['chunk']/'snapshot.jsonl')}
    key=digest(provenance);outcomes=[]
    async with connection.transaction():
        await connection.execute('select pg_advisory_xact_lock(20261023,1)')
        old=await connection.fetchval('select result from bilingual_gap_repair_batches where run_key=$1 and chunk=$2',root.name,job['chunk'])
        if old:
            old=json.loads(old)
            if old['provenance']!=provenance:raise ValueError('Committed review changed')
            return {**old,'repeat':True}
        for row in final:
            sid=row['sense_id'];sense=await connection.fetchrow('select * from senses where id=$1 for update',sid)
            ts=await connection.fetch('select * from sense_translations where sense_id=$1 order by id',sid)
            before={'sense':json.loads(await connection.fetchval('select to_jsonb(s) from senses s where id=$1',sid)),
                    'translations':json.loads(await connection.fetchval("select coalesce(jsonb_agg(to_jsonb(t) order by id),'[]') from sense_translations t where sense_id=$1",sid))}
            if digest(before)!=snapshots[sid]['snapshot_hash']:raise ValueError(f'Live source changed: {sid}')
            if sense['review_status']=='accepted' or any(t['review_status']=='accepted' for t in ts):
                raise ValueError(f'Cannot override human-accepted content: {sid}')
            if sense['merged_into_sense_id'] is not None or sense['review_status']=='rejected':
                raise ValueError(f'Inactive source sense: {sid}')
            action=row['decision']
            if action=='blocked':outcomes.append({'sense_id':sid,'decision':action,'reason':row['reason']});continue
            if action=='correct':
                source_id=await connection.fetchval("""insert into sources(source_key,name,source_type,version,notes)
                  values($1,'Independently reviewed bilingual gap repairs','aigc_derived','2026-10-23',
                    'Manual model authorship and independent model review; not human-approved.')
                  on conflict(source_key) do update set updated_at=now() returning id""",SOURCE)
                await connection.execute("update sense_translations set review_status='rejected',updated_at=now() where sense_id=$1 and lang in ('zh','en') and review_status<>'rejected'",sid)
                for lang in ['zh','en']:
                    t=row['translations'][lang]
                    await connection.execute("""insert into sense_translations
                     (sense_id,lang,gloss,explanation,source_id,external_id,confidence,review_status,translation_style,raw_payload)
                     values($1,$2,$3,$4,$5,$6,$7,'needs_review','learner_dictionary',$8::jsonb)
                     on conflict(sense_id,lang,source_id) where source_id is not null do update set
                      gloss=excluded.gloss,explanation=excluded.explanation,confidence=excluded.confidence,
                      review_status='needs_review',raw_payload=excluded.raw_payload,updated_at=now()""",
                     sid,lang,t['gloss'],t['explanation'],source_id,f'{root.name}:{sid}:{lang}',row['confidence'],
                     json.dumps({'provenance':provenance,'decision':row},ensure_ascii=False))
            after={'sense':dict(await connection.fetchrow('select * from senses where id=$1',sid)),
                   'translations':[dict(t) for t in await connection.fetch('select * from sense_translations where sense_id=$1 order by id',sid)]}
            await connection.execute("""insert into bilingual_gap_repair_audit
              (run_key,chunk,sense_id,review_key,action,proposal,before_state,after_state)
              values($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8::jsonb)""",root.name,job['chunk'],sid,key,action,
              json.dumps({'provenance':provenance,'decision':row},ensure_ascii=False),json.dumps(before,ensure_ascii=False,default=str),json.dumps(after,ensure_ascii=False,default=str))
            outcomes.append({'sense_id':sid,'decision':action})
        report={'chunk':job['chunk'],'committed_at':datetime.now(timezone.utc).isoformat(),'provenance':provenance,
                'count':len(outcomes),'correct':sum(x['decision']=='correct' for x in outcomes),
                'keep':sum(x['decision']=='keep' for x in outcomes),'blocked':sum(x['decision']=='blocked' for x in outcomes),'outcomes':outcomes}
        await connection.execute('insert into bilingual_gap_repair_batches(run_key,chunk,result) values($1,$2,$3::jsonb)',root.name,job['chunk'],json.dumps(report,ensure_ascii=False))
    return report


async def run(args):
    root=Path(args.run_dir).resolve();manifest=json.loads((root/'manifest.json').read_text());c=None
    if not args.validate:
        backup=root/'before-gap-repair.dump'
        if not backup.exists() or backup.stat().st_size<10000:raise ValueError('Pre-repair backup required')
        c=await asyncpg.connect(os.environ.get('DATABASE_URL','postgresql://postgres:postgres@127.0.0.1:54322/postgres'))
        await c.execute((ROOT/'supabase/migrations/20261023010000_bilingual_gap_repair_audit.sql').read_text())
    try:
        for job in manifest:
            if args.chunk and job['chunk']!=args.chunk:continue
            review=root/'reviews'/f"review-{job['reviewer']}-{job['chunk']}.json"
            if not review.exists():continue
            final,provenance=prepare(root,job)
            if args.validate:print(json.dumps({'chunk':job['chunk'],'validated':len(final)}));continue
            report=await apply(c,root,job,final,provenance)
            receipt=root/'imports'/f"{job['chunk']}.done.json"
            if not receipt.exists():receipt.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            if not report.get('repeat'):print(json.dumps({k:v for k,v in report.items() if k not in {'outcomes','provenance'}},ensure_ascii=False),flush=True)
    finally:
        if c:await c.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-dir',default='outputs/gap_repair_20261023');p.add_argument('--chunk');p.add_argument('--validate',action='store_true');asyncio.run(run(p.parse_args()))
