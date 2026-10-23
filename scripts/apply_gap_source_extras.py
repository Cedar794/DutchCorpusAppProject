#!/usr/bin/env python3
"""Apply independent source/example/lemma dispositions with a complete audit transaction."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import asyncpg
try:
    from .apply_english_source_repairs import apply_review
except ImportError:
    from apply_english_source_repairs import apply_review

ROOT=Path(__file__).resolve().parents[1]

async def run(root):
    path=root/'source-repairs/extras-candidates-R.json'
    candidate=json.loads(path.read_text());sha=hashlib.sha256(path.read_bytes()).hexdigest()
    reviewpath=root/'reviews/extras-review-C.json';review=json.loads(reviewpath.read_text())
    assert review['reviewer']!='R' and review['candidate_sha256']==sha
    decisions={x['sense_id']:x for x in [x for x in review['decisions'] if 'sense_id' in x]}
    assert set(decisions)=={x['sense_id'] for x in candidate['source_repairs']}
    final=[]
    for row in candidate['source_repairs']:
        decision=decisions[row['sense_id']]
        assert decision['verdict'] in {'approve','replace'} and decision['reason'].endswith('#aigc')
        if decision['verdict']=='replace':row=decision['replacement']
        assert row['sense_id']==decision['sense_id']
        for key in ['example_nl','example_zh']:assert row[key].endswith('#aigc')
        final.append(row)
    holds={x['lemma_id']:x for x in [x for x in review['decisions'] if 'lemma_id' in x]}
    assert set(holds)=={x['lemma_id'] for x in candidate['dispositions']}
    assert all(x['verdict']=='approve' and x['reason'].endswith('#aigc') for x in holds.values())
    audited={'reviewed_chunks':['extras'],'source_repairs':final,'author':'R','reviewer':review['reviewer'],
             'candidate_sha256':sha,'independent_review_sha256':hashlib.sha256(reviewpath.read_bytes()).hexdigest()}
    repairpath=root/'reviews/repair-extras-reviewed.json'
    serialized=json.dumps(audited,ensure_ascii=False,indent=2)+'\n'
    if repairpath.exists():assert repairpath.read_text()==serialized
    else:repairpath.write_text(serialized)
    samplepath=root/'source-repairs/example-candidates-R.json'
    sample=json.loads(samplepath.read_text())
    samplereview=json.loads((root/'reviews/examples-review-C.json').read_text())
    assert samplereview['reviewer']!='R' and samplereview['candidate_sha256']==hashlib.sha256(samplepath.read_bytes()).hexdigest()
    checked={x['sense_id']:x for x in samplereview['decisions']}
    assert set(checked)=={x['sense_id'] for x in sample['example_repairs']}
    samplefinal=[]
    for row in sample['example_repairs']:
        d=checked[row['sense_id']]
        assert d['verdict'] in {'approve','replace'} and d['reason'].endswith('#aigc')
        if d['verdict']=='replace':row=d['replacement']
        assert row['sense_id']==d['sense_id'] and row['example_nl'].endswith('#aigc') and row['example_zh'].endswith('#aigc')
        samplefinal.append(row)
    c=await asyncpg.connect('postgresql://postgres:postgres@127.0.0.1:54322/postgres')
    try:
        async with c.transaction():
            await c.execute('select pg_advisory_xact_lock(20261023,1)')
            await c.execute((ROOT/'supabase/migrations/20261023020000_gap_source_extras_audit.sql').read_text())
            before={}
            for row in final:
                sid=row['sense_id']
                before[sid]=await c.fetchval('''select jsonb_build_object('sense',to_jsonb(s),
                  'examples',(select coalesce(jsonb_agg(to_jsonb(e) order by id),'[]') from examples e where e.sense_id=s.id),
                  'example_translations',(select coalesce(jsonb_agg(to_jsonb(t) order by t.id),'[]') from example_translations t join examples e on e.id=t.example_id where e.sense_id=s.id))
                  from senses s where id=$1''',sid)
            source_report=await apply_review(c,root,repairpath)
            assert not source_report.get('retry')
            source_id=await c.fetchval("select id from sources where source_key='aigc_subagent_source_repair_v1'")
            for row in final:
                sid=row['sense_id']
                if await c.fetchval("select exists(select 1 from gap_source_extras_audit where run_key=$1 and kind='sense_examples' and target_id=$2)",root.name,sid):continue
                await c.execute('update examples set is_active=false,updated_at=now() where sense_id=$1',sid)
                eid=await c.fetchval('''insert into examples(sense_id,ex_nl,source_id,external_id,quality_score,is_active,raw_payload)
                  values($1,$2,$3,$4,$5,true,$6::jsonb) returning id''',sid,row['example_nl'],source_id,f'{root.name}:{sid}:example',row['confidence'],json.dumps(audited,ensure_ascii=False))
                await c.execute("insert into example_translations(example_id,lang,translation,source_id,external_id) values($1,'zh',$2,$3,$4)",eid,row['example_zh'],source_id,f'{root.name}:{sid}:example:zh')
                after=await c.fetchval('''select jsonb_build_object('sense',to_jsonb(s),
                  'examples',(select coalesce(jsonb_agg(to_jsonb(e) order by id),'[]') from examples e where e.sense_id=s.id),
                  'example_translations',(select coalesce(jsonb_agg(to_jsonb(t) order by t.id),'[]') from example_translations t join examples e on e.id=t.example_id where e.sense_id=s.id))
                  from senses s where id=$1''',sid)
                await c.execute("insert into gap_source_extras_audit(run_key,kind,target_id,before_state,after_state,proposal) values($1,'sense_examples',$2,$3::jsonb,$4::jsonb,$5::jsonb)",root.name,sid,before[sid],after,json.dumps({'row':row,'review':decisions[sid]},ensure_ascii=False))
            for row in samplefinal:
                sid=row['sense_id']
                if await c.fetchval("select exists(select 1 from gap_source_extras_audit where run_key=$1 and kind='sample_examples' and target_id=$2)",root.name,sid):continue
                old=await c.fetchval("select coalesce(jsonb_agg(to_jsonb(e) order by id),'[]') from examples e where sense_id=$1",sid)
                await c.execute('update examples set is_active=false,updated_at=now() where sense_id=$1',sid)
                eid=await c.fetchval("insert into examples(sense_id,ex_nl,source_id,external_id,quality_score,is_active,raw_payload) values($1,$2,$3,$4,.85,true,$5::jsonb) returning id",sid,row['example_nl'],source_id,f'{root.name}:{sid}:example',json.dumps({'proposal':row,'review':checked[sid]},ensure_ascii=False))
                await c.execute("insert into example_translations(example_id,lang,translation,source_id,external_id) values($1,'zh',$2,$3,$4)",eid,row['example_zh'],source_id,f'{root.name}:{sid}:example:zh')
                after=await c.fetchval("select coalesce(jsonb_agg(to_jsonb(e) order by id),'[]') from examples e where sense_id=$1",sid)
                await c.execute("insert into gap_source_extras_audit(run_key,kind,target_id,before_state,after_state,proposal) values($1,'sample_examples',$2,$3::jsonb,$4::jsonb,$5::jsonb)",root.name,sid,old,after,json.dumps({'proposal':row,'review':checked[sid]},ensure_ascii=False))
            for row in candidate['dispositions']:
                lid=row['lemma_id']
                if await c.fetchval("select exists(select 1 from gap_source_extras_audit where run_key=$1 and kind='lemma_hold' and target_id=$2)",root.name,lid):continue
                assert not await c.fetchval("select exists(select 1 from senses where lemma_id=$1 and merged_into_sense_id is null and review_status<>'rejected')",lid)
                before_l=await c.fetchval('select to_jsonb(l) from lemmas l where id=$1 for update',lid)
                await c.execute("update lemmas set review_status='needs_review',needs_review=true,notes=concat_ws(E'\\n',notes,$2::text),updated_at=now() where id=$1",lid,row['reason'])
                after_l=await c.fetchval('select to_jsonb(l) from lemmas l where id=$1',lid)
                await c.execute("insert into gap_source_extras_audit(run_key,kind,target_id,before_state,after_state,proposal) values($1,'lemma_hold',$2,$3::jsonb,$4::jsonb,$5::jsonb)",root.name,lid,before_l,after_l,json.dumps({'row':row,'review':holds[lid]},ensure_ascii=False))
        report={'source_corrections':len(final),'held_lemmas':len(holds),'sample_example_repairs':len(samplefinal),'source_report':source_report,'human_reviewed':False}
        (root/'source-repairs/extras-application.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='source_report'}))
    finally:await c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',default=str(ROOT/'outputs/gap_repair_20261023'));asyncio.run(run(Path(p.parse_args().run_dir)))
