#!/usr/bin/env python3
"""Export English gaps, validate subagent files, and import only still-missing translations.

This script never generates language content. Subagents author the output JSONL.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

import asyncpg

DEFAULT_RUN = Path('outputs/english_completion_20261022')
SOURCE_KEY = 'aigc_subagent_english_v1'

INPUT_QUERY = """
select s.id sense_id,l.lemma,l.level,coalesce(p.pos,'') pos,
coalesce(nullif(btrim(s.display_definition_nl),''),s.definition_nl,'') definition_nl,
coalesce(s.usage_note,'') usage_note,src.source_key,
coalesce(zh.gloss,'') gloss_zh,coalesce(ex.ex_nl,'') example_nl
from public.senses s join public.lemmas l on l.id=s.lemma_id
left join public.lemma_pos_entries p on p.id=s.lemma_pos_entry_id
join public.sources src on src.id=s.source_id
left join lateral(select gloss from public.sense_translations
  where sense_id=s.id and lang='zh' order by updated_at desc,id desc limit 1) zh on true
left join lateral(select ex_nl from public.examples where sense_id=s.id order by id limit 1) ex on true
where s.merged_into_sense_id is null and s.review_status<>'rejected'
and not exists(select 1 from public.sense_translations t
  where t.sense_id=s.id and t.lang='en' and t.review_status<>'rejected' and btrim(t.gloss)<>'')
order by l.level,coalesce(l.cc100_freq,l.subtlex_freq,0) desc,l.lemma,s.id
"""


def input_hash(row):
    return hashlib.sha256(json.dumps({k:v for k,v in row.items() if k != 'input_hash'},
                                    ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def write_json(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')


def validate_chunk(directory):
    inputs=read_jsonl(directory/'input.jsonl')
    outputs=read_jsonl(directory/'output.jsonl')
    by_id={r['sense_id']:r for r in inputs}
    if len(by_id) != len(inputs): raise ValueError(f'{directory}: duplicate input IDs')
    if len(outputs) != len(inputs): raise ValueError(f'{directory}: incomplete output')
    seen=set()
    for row in outputs:
        sid=row.get('sense_id')
        if type(sid) is not int or sid not in by_id or sid in seen:
            raise ValueError(f'{directory}: invalid or duplicate sense_id {sid}')
        seen.add(sid)
        if row.get('input_hash') != input_hash(by_id[sid]):
            raise ValueError(f'{directory}: hash mismatch {sid}')
        if row.get('status') not in {'draft','blocked'}:
            raise ValueError(f'{directory}: invalid status {sid}')
        conf=row.get('confidence')
        if type(conf) not in (int,float) or not math.isfinite(conf) or not 0 <= conf <= 1:
            raise ValueError(f'{directory}: invalid confidence {sid}')
        for field in ['gloss','explanation','quality_note']:
            value=row.get(field)
            if not isinstance(value,str) or len(value)>2000 or '\n' in value or '\t' in value:
                raise ValueError(f'{directory}: invalid {field} {sid}')
            if value and (not value.endswith('#aigc') or not value.removesuffix('#aigc').strip()):
                raise ValueError(f'{directory}: missing marker/empty {field} {sid}')
        if not row['quality_note']:
            raise ValueError(f'{directory}: missing quality note {sid}')
        if row['status']=='draft':
            for field in ['gloss','explanation']:
                if not re.search('[A-Za-z]',row[field]) or re.search('[\u4e00-\u9fff]',row[field]):
                    raise ValueError(f'{directory}: non-English {field} {sid}')
            if len(row['gloss'])>250:
                raise ValueError(f'{directory}: gloss too long {sid}')
        elif row['gloss'] or row['explanation'] or conf>.4:
            raise ValueError(f'{directory}: blocked row must not have translation {sid}')
    return inputs,outputs


def apply_reviews(run_dir, directories, review_names):
    chunks={d.name:(d,*validate_chunk(d)) for d in directories}
    outputs={name:{r['sense_id']:dict(r) for r in chunk[2]} for name,chunk in chunks.items()}
    covered=set();applied=[]
    allowed={'status','gloss','explanation','confidence','quality_note'}
    for name in review_names:
        review=json.loads((run_dir/'reviews'/name).read_text(encoding='utf-8'))
        reviewed=review['reviewed_chunks']
        if len(reviewed)!=len(set(reviewed)) or not set(reviewed)<=set(chunks):
            raise ValueError('Review contains unknown or duplicate chunks')
        expected=sum(len(chunks[n][1]) for n in reviewed)
        if review['reviewed_count']!=expected: raise ValueError('Incomplete review coverage')
        covered.update(reviewed)
        for change in review['corrections']:
            chunk=change['chunk'];sid=change['sense_id'];fields=change['fields']
            if chunk not in reviewed or sid not in outputs[chunk] or not change['reason'].strip():
                raise ValueError('Invalid review target/reason')
            if not fields or not set(fields)<=allowed: raise ValueError('Review cannot change identity/hash')
            outputs[chunk][sid].update(fields)
            applied.append({'review':name,**change})
    if covered!=set(chunks): raise ValueError('Every selected chunk needs review coverage')
    # Validate every proposed file before modifying any originals.
    with tempfile.TemporaryDirectory() as temp:
        for name,(directory,inputs,old_outputs) in chunks.items():
            target=Path(temp)/name
            write_jsonl(target/'input.jsonl',inputs)
            write_jsonl(target/'output.jsonl',[outputs[name][r['sense_id']] for r in old_outputs])
            validate_chunk(target)
        for name,(directory,_,_) in chunks.items():
            original=directory/'output.pre-review.jsonl'
            if not original.exists(): original.write_bytes((directory/'output.jsonl').read_bytes())
            pending=directory/'output.pending'
            pending.write_bytes((Path(temp)/name/'output.jsonl').read_bytes())
            pending.replace(directory/'output.jsonl')
    write_json(run_dir/'review-application.json',{
        'review_files':review_names,'reviewed_chunks':sorted(covered),
        'reviewed_count':sum(len(c[1]) for c in chunks.values()),
        'output_sha256':{name:hashlib.sha256((chunk[0]/'output.jsonl').read_bytes()).hexdigest()
                         for name,chunk in chunks.items()},
        'corrections_count':len(applied),'corrections':applied,'human_reviewed':False})
    return {'reviewed_chunks':len(covered),'corrections_count':len(applied)}


async def load_inputs(connection):
    rows=[dict(r) for r in await connection.fetch(INPUT_QUERY)]
    for row in rows: row['input_hash']=input_hash(row)
    return rows


async def counts(connection):
    return dict(await connection.fetchrow("""
      select count(*) total_senses,
      count(*) filter(where s.merged_into_sense_id is null and s.review_status<>'rejected') active_senses,
      count(*) filter(where s.review_status='rejected') rejected_senses,
      count(*) filter(where not exists(select 1 from public.sense_translations t
        where t.sense_id=s.id and t.lang='en' and t.review_status<>'rejected' and btrim(t.gloss)<>'')) missing_en_all,
      count(*) filter(where s.merged_into_sense_id is null and s.review_status<>'rejected' and not exists(
        select 1 from public.sense_translations t where t.sense_id=s.id and t.lang='en' and t.review_status<>'rejected'
        and btrim(t.gloss)<>'')) missing_en_active
      from public.senses s
    """))


async def run(args):
    run_dir=Path(args.run_dir)
    if args.action=='export':
        if (run_dir/'queue.jsonl').exists():
            raise ValueError('Run already exported. Use a new run directory; do not overwrite work.')
    if args.action!='export':
        directories=[run_dir/'chunks'/name for name in args.chunks.split(',')]
        chunks=[(d,*validate_chunk(d)) for d in directories]
        all_ids=[row['sense_id'] for _,inputs,_ in chunks for row in inputs]
        if len(set(all_ids))!=len(all_ids): raise ValueError('Repeated chunks/IDs')
        summary={'checked_chunks':[d.name for d,_,_ in chunks],
                 'counts':dict(Counter(r['status'] for _,_,rows in chunks for r in rows)),
                 'format_validation_only':True}
        if args.action=='apply-reviews':
            if not args.reviews: raise ValueError('--reviews is required')
            print(json.dumps(apply_reviews(run_dir,directories,args.reviews.split(',')),indent=2));return
        if args.action=='validate':
            write_json(run_dir/'last-validation.json',summary)
            print(json.dumps(summary,indent=2));return
        review_path=run_dir/'review-application.json'
        if not review_path.is_file(): raise ValueError('Apply cross-reviews before importing')
        applied_review=json.loads(review_path.read_text(encoding='utf-8'))
        if not set(args.chunks.split(','))<=set(applied_review['reviewed_chunks']):
            raise ValueError('Selected chunks lack cross-review coverage')
        for directory,_,_ in chunks:
            actual=hashlib.sha256((directory/'output.jsonl').read_bytes()).hexdigest()
            if actual!=applied_review['output_sha256'].get(directory.name):
                raise ValueError('Output changed after cross-review; re-review before importing')
        if not args.backup or not Path(args.backup).is_file() or Path(args.backup).stat().st_size<100:
            raise ValueError('A verified pre-import pg_dump file is required via --backup')
        if Path(args.backup).read_bytes()[:5]!=b'PGDMP':
            raise ValueError('Backup must be a PostgreSQL custom-format dump')
    url=os.environ.get('DATABASE_URL','postgresql://postgres:postgres@127.0.0.1:54322/postgres')
    connection=await asyncpg.connect(url,command_timeout=60)
    try:
        if args.action=='export':
            rows=await load_inputs(connection)
            write_jsonl(run_dir/'queue.jsonl',rows)
            for n in range(0,len(rows),100):
                write_jsonl(run_dir/'chunks'/f'{n//100+1:04d}'/'input.jsonl',rows[n:n+100])
            write_json(run_dir/'export.json',{'exported_at':datetime.now(timezone.utc).isoformat(),
                'counts':await counts(connection),'selected':len(rows),'chunk_size':100,
                'by_level':dict(Counter(str(r['level']) for r in rows))})
            print(len(rows));return
        async with connection.transaction():
            await connection.execute('select pg_advisory_xact_lock(20261022,2)')
            await connection.fetch('select id from public.senses where id=any($1::bigint[]) for update',all_ids)
            current={r['sense_id']:r for r in await load_inputs(connection)}
            before=await counts(connection)
            source_id=await connection.fetchval("""
              insert into public.sources(source_key,name,source_type,version,notes)
              values($1,'Subagent-authored English sense translations','aigc_derived','2026-10-22',
                     'Model-generated English drafts; not human-approved. Source snapshots and quality notes in raw_payload.')
              on conflict(source_key) do update set updated_at=now() returning id
            """,SOURCE_KEY)
            imported=[];skipped=[];blocked=[];output_hashes={}
            for directory,inputs,outputs in chunks:
                by_id={r['sense_id']:r for r in inputs}
                output_hashes[directory.name]=hashlib.sha256((directory/'output.jsonl').read_bytes()).hexdigest()
                for row in outputs:
                    sid=row['sense_id']
                    if row['status']=='blocked': blocked.append(row);continue
                    if sid not in current: skipped.append(sid);continue
                    if current[sid]['input_hash']!=row['input_hash']:
                        raise ValueError(f'Source changed since export: {sid}. Re-review before importing.')
                    payload={'generation_method':'subagent_authored','human_reviewed':False,
                             'batch':run_dir.name,'chunk':directory.name,
                             'cross_reviewed_by_model':True,
                             'review_report_sha256':hashlib.sha256(review_path.read_bytes()).hexdigest(),
                             'input':by_id[sid],'output':row}
                    inserted=await connection.fetchval("""
                       insert into public.sense_translations(sense_id,lang,gloss,explanation,source_id,
                         external_id,confidence,review_status,translation_style,raw_payload)
                       select $1,'en',$2,$3,$4,$5,$6,$7,'learner_dictionary',$8::jsonb
                       where not exists(select 1 from public.sense_translations where sense_id=$1
                         and lang='en' and review_status<>'rejected' and btrim(gloss)<>'')
                       on conflict (sense_id,lang,source_id) where source_id is not null do nothing
                       returning id
                    """,sid,row['gloss'],row['explanation'],source_id,f'{run_dir.name}:{sid}:en',
                       row['confidence'],'needs_review',
                       json.dumps(payload,ensure_ascii=False))
                    if inserted: imported.append({'sense_id':sid,'translation_id':inserted})
                    else: skipped.append(sid)
            after=await counts(connection)
            if before['missing_en_active']-after['missing_en_active']!=len(imported):
                raise RuntimeError('Unexpected gap change: rolling back')
            report={'imported_at':datetime.now(timezone.utc).isoformat(),
                    'source_key':SOURCE_KEY,'before':before,'after':after,
                    'imported_count':len(imported),'imported':imported,
                    'skipped_existing_or_inactive':skipped,'blocked_count':len(blocked),
                    'output_sha256':output_hashes,'backup':str(Path(args.backup).resolve()),
                    'human_reviewed':False}
        # Database commit succeeded; reports are an additional local audit trail.
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        write_json(run_dir/'imports'/f'{stamp}.json',report)
        write_jsonl(run_dir/'blocked'/f'{stamp}.jsonl',blocked)
        print(json.dumps({k:v for k,v in report.items() if k!='imported'},ensure_ascii=False,indent=2))
    finally:
        await connection.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['export','validate','apply-reviews','import'])
    parser.add_argument('--run-dir',default=str(DEFAULT_RUN))
    parser.add_argument('--chunks',help='Explicit comma-separated chunk names, e.g. 0001,0002')
    parser.add_argument('--reviews',help='Comma-separated review JSON filenames in run-dir/reviews')
    parser.add_argument('--backup',help='Pre-import custom-format PostgreSQL dump')
    args=parser.parse_args()
    if args.action!='export' and not args.chunks: parser.error('--chunks is required')
    asyncio.run(run(args))


if __name__=='__main__':
    main()
