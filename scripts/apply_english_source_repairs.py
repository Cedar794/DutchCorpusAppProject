#!/usr/bin/env python3
"""Apply explicit cross-review source repairs after their translation batch committed."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

import asyncpg
try:
    from .complete_english_translations import write_json
except ImportError:
    from complete_english_translations import write_json

ROOT=Path(__file__).resolve().parents[1]
POS_ALIASES = {'CCONJ': 'CONJ'}


def validate_proposal(row):
    if type(row.get('sense_id')) is not int or row['sense_id']<1:
        raise ValueError('Invalid sense ID')
    if row.get('action') not in {'reject_mapping','correct'}:
        raise ValueError('Invalid repair action')
    for key in ['reason','evidence']:
        if not isinstance(row.get(key),str) or not row[key].endswith('#aigc'):
            raise ValueError('Repair requires marked reason and evidence')
    if 'preserve_external_synset' in row and type(row['preserve_external_synset']) is not bool:
        raise ValueError('Synset preservation flag must be boolean')
    if row['action']=='correct':
        if 'explanation_zh' in row and (not isinstance(row['explanation_zh'],str) or not row['explanation_zh'].endswith('#aigc')):
            raise ValueError('Chinese explanation must retain its generation marker')
        for key in ['definition_nl','usage_note','gloss_en','explanation_en','gloss_zh']:
            if not isinstance(row.get(key),str) or not row[key].endswith('#aigc'):
                raise ValueError('Correction is incomplete')
        if row.get('pos') not in {'NOUN','VERB','ADJ','ADV','ADP','DET','PRON','NUM','CONJ','CCONJ','INTJ','PROPN','ABBR','PART','PRONOM-DEM','AUX','SCONJ','PREFIX'}:
            raise ValueError('Correction requires a known POS')
        if type(row.get('confidence')) not in (int,float) or not 0<=row['confidence']<=.9:
            raise ValueError('Correction confidence must be between 0 and 0.9')


def effective_proposals(root, path, review):
    """Honor evidence-based withdrawals without mutating published review files."""
    proposals=review.get('source_repairs',[])
    retracted=[]
    ledger=root/'source-repair-retractions.json'
    if ledger.exists():
        key=hashlib.sha256(path.read_bytes()).hexdigest()
        ids={row['sense_id'] for row in proposals}
        for entry in json.loads(ledger.read_text()).get('retractions',[]):
            if entry['review']!=path.name:continue
            if entry['review_sha256']!=key:raise ValueError('Retraction review hash changed')
            if entry['sense_id'] not in ids or not entry.get('reason','').endswith('#aigc'):
                raise ValueError('Invalid source proposal retraction')
            retracted.append(entry)
    excluded={entry['sense_id'] for entry in retracted}
    return [row for row in proposals if row['sense_id'] not in excluded],retracted


async def apply_review(connection,root,path):
    review=json.loads(path.read_text())
    proposals,retracted=effective_proposals(root,path,review)
    if not proposals and not retracted:return None
    ids=set()
    for name in review['reviewed_chunks']:
        ids.update(r['sense_id'] for r in map(json.loads,(root/'chunks'/name/'input.jsonl').read_text().splitlines()))
    for row in proposals:
        validate_proposal(row)
        if row['sense_id'] not in ids:raise ValueError('Repair outside reviewed batch')
    key=hashlib.sha256(path.read_bytes()).hexdigest()
    outcomes=[]
    async with connection.transaction():
        if not await connection.fetchval('select pg_try_advisory_xact_lock(20261022,2)'):
            return {'retry':'importer_busy'}
        await connection.execute((ROOT/'supabase/migrations/20261022080000_english_source_repair_audit.sql').read_text())
        for proposal in proposals:
            sid=proposal['sense_id']
            if await connection.fetchval('select exists(select 1 from english_source_repair_audit where sense_id=$1 and review_key=$2)',sid,key):
                continue
            sense=await connection.fetchrow('select * from public.senses where id=$1 for update',sid)
            if not sense or sense['merged_into_sense_id'] is not None:raise ValueError('Invalid repair target')
            if sense['review_status']=='accepted':raise ValueError('Cannot override an accepted sense automatically')
            translations=await connection.fetch('select * from public.sense_translations where sense_id=$1 order by id',sid)
            if any(r['review_status']=='accepted' for r in translations):
                raise ValueError('Cannot override an accepted translation automatically')
            before={'sense':dict(sense),'translations':[dict(r) for r in translations]}
            before_json=json.dumps(before,ensure_ascii=False,default=str)
            metadata={'method':'model_cross_review','human_reviewed':False,
                      'review':path.name,'review_sha256':key,'proposal':proposal}
            if proposal['action']=='reject_mapping':
                # Correct an invalid source association without deleting its historical row.
                await connection.execute("""update public.senses set review_status='rejected',
                  raw_payload=raw_payload||jsonb_build_object('english_source_repair',$2::jsonb),updated_at=now()
                  where id=$1""",sid,json.dumps(metadata,ensure_ascii=False))
                await connection.execute("update public.sense_translations set review_status='rejected',updated_at=now() where sense_id=$1",sid)
            else:
                pos_tag=POS_ALIASES.get(proposal['pos'],proposal['pos'])
                metadata['normalized_pos']=pos_tag
                pos_id=await connection.fetchval('select id from public.lemma_pos_entries where lemma_id=$1 and pos=$2',sense['lemma_id'],pos_tag)
                if not pos_id:
                    pos_id=await connection.fetchval("""insert into public.lemma_pos_entries
                      (lemma_id,pos,pos_source,pos_confidence,needs_review,notes)
                      values($1,$2,'aigc_source_repair_v1',$3,true,$4) returning id""",
                      sense['lemma_id'],pos_tag,proposal['confidence'],proposal['reason'])
                await connection.execute("""update public.senses set display_definition_nl=$2,usage_note=$3,
                  lemma_pos_entry_id=$4,external_synset_id=case when $7::boolean then external_synset_id else null end,review_status='needs_review',confidence=$5,
                  raw_payload=raw_payload||jsonb_build_object('english_source_repair',$6::jsonb),updated_at=now()
                  where id=$1""",sid,proposal['definition_nl'],proposal['usage_note'],pos_id,
                  proposal['confidence'],json.dumps(metadata,ensure_ascii=False),proposal.get('preserve_external_synset',False))
                source=await connection.fetchval("""insert into sources(source_key,name,source_type,version,notes)
                  values('aigc_subagent_source_repair_v1','Cross-reviewed lexical source repairs','aigc_derived',
                    '2026-10-22','Model cross-review; not human-approved.')
                  on conflict(source_key) do update set updated_at=now() returning id""")
                # Keep superseded translations auditable and prefer the newly repaired source.
                await connection.execute("update public.sense_translations set review_status='rejected',updated_at=now() where sense_id=$1",sid)
                for lang,gloss,explanation in [('en',proposal['gloss_en'],proposal['explanation_en']),
                                               ('zh',proposal['gloss_zh'],proposal.get('explanation_zh',proposal['gloss_zh']))]:
                    await connection.execute("""insert into sense_translations
                      (sense_id,lang,gloss,explanation,source_id,external_id,confidence,review_status,translation_style,raw_payload)
                      values($1,$2,$3,$4,$5,$6,$7,'needs_review','learner_dictionary',$8::jsonb)
                      on conflict(sense_id,lang,source_id) where source_id is not null do update set
                       gloss=excluded.gloss,explanation=excluded.explanation,confidence=excluded.confidence,
                       review_status='needs_review',raw_payload=excluded.raw_payload,updated_at=now()""",
                      sid,lang,gloss,explanation,source,f'source-repair:{sid}:{lang}',proposal['confidence'],
                      json.dumps(metadata,ensure_ascii=False))
            after_sense=await connection.fetchval('select to_jsonb(s) from senses s where id=$1',sid)
            after_translations=await connection.fetchval("select coalesce(jsonb_agg(to_jsonb(t) order by id),'[]') from sense_translations t where sense_id=$1",sid)
            after_json=json.dumps({'sense':json.loads(after_sense),'translations':json.loads(after_translations)},ensure_ascii=False)
            await connection.execute("""insert into english_source_repair_audit
              (sense_id,review_key,action,proposal,before_state,after_state)
              values($1,$2,$3,$4::jsonb,$5::jsonb,$6::jsonb)""",sid,key,proposal['action'],
              json.dumps(proposal,ensure_ascii=False),before_json,after_json)
            outcomes.append({'sense_id':sid,'action':proposal['action']})
    report={'review':path.name,'review_sha256':key,'outcomes':outcomes,'count':len(outcomes),
            'retracted_source_proposals':retracted}
    write_json(root/'source-repairs'/(path.stem+'.done.json'),report)
    return report


async def run(args):
    root=Path(args.run_dir).resolve()
    connection=await asyncpg.connect(os.environ.get('DATABASE_URL','postgresql://postgres:postgres@127.0.0.1:54322/postgres'),command_timeout=60)
    try:
        reports=[]
        if args.review:
            paths=[root/'reviews'/args.review]
        else:
            paths=[root/'reviews'/json.loads(done.read_text())['review']
                   for done in sorted((root/'batch-control').glob('*.done.json'))]
        for path in paths:
            if (root/'source-repairs'/(path.stem+'.done.json')).exists():continue
            report=await apply_review(connection,root,path)
            if report and report.get('retry'):
                break
            if report:reports.append(report)
        print(json.dumps(reports,ensure_ascii=False,indent=2))
    finally:await connection.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review',help='Explicit supplemental independently reviewed repair file')
    parser.add_argument('--run-dir',default='outputs/english_completion_20261022')
    asyncio.run(run(parser.parse_args()))
