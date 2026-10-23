#!/usr/bin/env python3
"""Apply independently reviewed source research in small, fingerprint-checked transactions."""
import argparse,asyncio,hashlib,json,os,unicodedata
from pathlib import Path
import asyncpg
ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'outputs/source_gap_research_20261023'
FIELDS=['definition_nl','usage_note','gloss_en','explanation_en','gloss_zh','explanation_zh','example_nl','example_zh']
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def marked(x):return isinstance(x,str) and x.endswith('#aigc') and bool(x[:-5].strip())
def execution_payload(final):
    """Derive every executable field from the immutable, independently reviewed item."""
    if final.get('sense'):
        p=dict(final['sense'])
        p['display_lemma']=final.get('recovered_display_form')
        if final.get('canonical_repair'):
            p['canonical_repair']=final['canonical_repair']
            p['quarantine_form_ids']=final['form_repair']['quarantine_form_ids']
            p['quarantine_pos_entry_ids']=final['form_repair']['quarantine_pos_entry_ids']
        return 'restore_lemma',p
    if final['target_id'].startswith('relation:'):
        p=dict(final['preferred_representation'])
        p['entry_kind']={'expression':'lexical_expression','sense_definition':'definition_note','usage_pattern':'usage_construction','example':'usage_example'}[p['layer']]
        p['expression_type']=p['kind'];p['expression_nl']=p['text_nl']
        p['sense_id']=final['source_scope'].get('preferred_example_sense_id',final['source_scope']['sense_id'])
        p['import_status']=final['executable_disposition']['expected_import_status']
        return 'store_expression',p
    assert final['disposition']=='defer'
    return 'defer',None
def validate_item(x):
    kind,number=x['target_id'].split(':');assert kind in {'lemma','relation','new_sense'} and number.isdigit()
    assert x['action'] in {'restore_lemma','store_expression','defer'}
    assert type(x['confidence']) in (int,float) and 0<=x['confidence']<=.9 and marked(x['reason'])
    assert x['author']!=x['reviewer'] and x.get('evidence')
    if x['action']=='defer':assert x.get('payload') is None;return
    p=x['payload'];assert all(marked(p.get(k)) for k in FIELDS)
    assert any('\u3400'<=ch<='\u9fff' for ch in p['gloss_zh'])
    if x['action']=='restore_lemma':
        assert kind=='lemma' and p['pos'] in {'PROPN','NOUN','N','ABBR'}
        if p.get('canonical_repair'):
            repair=p['canonical_repair'];assert repair['old_lemma_norm']!=repair['new_lemma_norm']
            assert repair['new_lemma_norm']==unicodedata.normalize('NFC',repair['new_lemma'].lower().strip())
    else:
        assert kind=='relation' and p['entry_kind'] in {'lexical_expression','usage_construction','definition_note','usage_example'}
        assert marked(p.get('expression_nl')) and p.get('sense_id') and p.get('import_status')
async def snapshot(c,target):
    kind,number=target.split(':');n=int(number)
    if kind=='lemma':
        val=await c.fetchval("""select jsonb_build_object('lemma',to_jsonb(l),
          'pos_entries',(select coalesce(jsonb_agg(to_jsonb(p) order by id),'[]') from lemma_pos_entries p where lemma_id=l.id),
          'forms',(select coalesce(jsonb_agg(to_jsonb(f)||jsonb_build_object('is_active',coalesce(to_jsonb(f)->'is_active','true'::jsonb)) order by id),'[]') from forms f where lemma_id=l.id),
          'senses',(select coalesce(jsonb_agg(to_jsonb(s) order by id),'[]') from senses s where lemma_id=l.id),
          'translations',(select coalesce(jsonb_agg(to_jsonb(t) order by t.id),'[]') from sense_translations t join senses s on s.id=t.sense_id where s.lemma_id=l.id),
          'examples',(select coalesce(jsonb_agg(to_jsonb(e) order by e.id),'[]') from examples e join senses s on s.id=e.sense_id where s.lemma_id=l.id))
          from lemmas l where id=$1""",n)
    else:
        table='aigc_relation_candidates' if kind=='relation' else 'aigc_new_sense_candidates'
        val=await c.fetchval(f'select to_jsonb(t) from {table} t where id=$1',n)
    assert val is not None;return json.loads(val)
def load_plan(root):
    plan=json.loads((root/'approved-plan.json').read_text())
    assert plan['embedding_enabled'] is False and plan['human_reviewed'] is False
    context=json.loads((root/'context.json').read_text())
    expected={f"lemma:{x['lemma']['id']}" for x in context['held_lemmas']}|{f"relation:{x['id']}" for x in context['relations']}|{f"new_sense:{x['id']}" for x in context['new_senses']}
    assert expected and len(plan['items'])==len(expected) and {x['target_id'] for x in plan['items']}==expected
    assert len(plan['proofs'])==3 and {x['author'] for x in plan['proofs']}=={'A','B','C'}
    for proof in plan['proofs']:
        for k in ['candidate','review']:
            p=root/proof[k];assert hashlib.sha256(p.read_bytes()).hexdigest()==proof[k+'_sha256']
        review=json.loads((root/proof['review']).read_text());assert review['reviewer']!=proof['author']
        assert review.get('candidate_sha256',review.get('proposal_sha256'))==proof['candidate_sha256']
        candidate=json.loads((root/proof['candidate']).read_text())
        assert candidate['author']==proof['author']
        byid={x['target_id']:x for x in review['decisions']}
        assert len(byid)==len(review['decisions'])==len(candidate['items'])
        assert set(byid)=={x['target_id'] for x in candidate['items']}
        assert {x['target_id'] for x in plan['items'] if x['author']==proof['author']}==set(byid)
        for item in candidate['items']:
            decision=byid[item['target_id']];assert marked(decision['reason'])
            verdict=decision.get('verdict',decision.get('decision'));assert verdict in {'approve','replace'}
            final=decision['replacement'] if verdict=='replace' else item
            assert final['target_id']==item['target_id']
            normalized=next(x for x in plan['items'] if x['target_id']==item['target_id'])
            assert normalized['reviewed_item_sha256']==digest(final) and normalized['reviewer']==review['reviewer']
            action,payload=execution_payload(final)
            assert normalized['action']==action and normalized['payload']==payload
            assert normalized['reason']==final['reason'] and normalized['evidence']==final['evidence']
            assert normalized['confidence']==final['confidence']
    for x in plan['items']:validate_item(x)
    return plan
async def restore_lemma(c,root,x,source):
    lid=int(x['target_id'].split(':')[1]);p=x['payload'];old=await c.fetchrow('select * from lemmas where id=$1 for update',lid)
    assert old['review_status']=='needs_review';assert not await c.fetchval("select exists(select 1 from senses where lemma_id=$1 and merged_into_sense_id is null and review_status<>'rejected')",lid)
    repair=p.get('canonical_repair')
    if repair:
        assert old['lemma_norm']==repair['old_lemma_norm'] and old['level']==repair['retain_level']
        assert not await c.fetchval('select exists(select 1 from lemmas where lemma_norm=$1 and id<>$2)',repair['new_lemma_norm'],lid)
        await c.execute('update lemmas set lemma=$2,lemma_norm=$3,display_lemma=$4,word_family=$3,updated_at=now() where id=$1',lid,repair['new_lemma'],repair['new_lemma_norm'],repair['new_display_lemma'])
        for fid in p.get('quarantine_form_ids',[]):
            assert await c.fetchval('select lemma_id=$2 from forms where id=$1',fid,lid)
            await c.execute("update forms set is_active=false,needs_review=true,raw_payload=raw_payload||jsonb_build_object('source_research_quarantine',$2::jsonb),updated_at=now() where id=$1",fid,json.dumps({'run':root.name,'reason':x['reason'],'human_reviewed':False},ensure_ascii=False))
        for pid in p.get('quarantine_pos_entry_ids',[]):
            assert await c.fetchval('select lemma_id=$2 from lemma_pos_entries where id=$1',pid,lid)
            await c.execute('update lemma_pos_entries set needs_review=true,is_primary=false,notes=concat_ws(E\'\\n\',notes,$2::text),updated_at=now() where id=$1',pid,x['reason'])
    posid=await c.fetchval('select id from lemma_pos_entries where lemma_id=$1 and pos=$2',lid,p['pos'])
    if not posid:
        posid=await c.fetchval("insert into lemma_pos_entries(lemma_id,pos,pos_source,pos_confidence,needs_review,notes) values($1,$2,'aigc_verified_source_research_v1',$3,true,$4) returning id",lid,p['pos'],x['confidence'],p['usage_note'])
    await c.execute('update lemma_pos_entries set is_primary=(id=$2),updated_at=now() where lemma_id=$1 and is_primary is distinct from (id=$2)',lid,posid)
    metadata={'run':root.name,'decision':x,'human_reviewed':False}
    sid=await c.fetchval("""insert into senses(lemma_id,lemma_pos_entry_id,source_id,external_id,definition_nl,display_definition_nl,usage_note,confidence,review_status,is_primary,raw_payload)
      values($1,$2,$3,$4,$5,$5,$6,$7,'needs_review',true,$8::jsonb) returning id""",lid,posid,source,f'{root.name}:{x["target_id"]}',p['definition_nl'],p['usage_note'],x['confidence'],json.dumps(metadata,ensure_ascii=False))
    for lang in ['en','zh']:
        await c.execute("""insert into sense_translations(sense_id,lang,gloss,explanation,source_id,external_id,confidence,review_status,translation_style,raw_payload)
          values($1,$2,$3,$4,$5,$6,$7,'needs_review','learner_dictionary',$8::jsonb)""",sid,lang,p['gloss_'+lang],p['explanation_'+lang],source,f'{root.name}:{lid}:{lang}',x['confidence'],json.dumps(metadata,ensure_ascii=False))
    eid=await c.fetchval('insert into examples(sense_id,ex_nl,source_id,external_id,quality_score,raw_payload) values($1,$2,$3,$4,$5,$6::jsonb) returning id',sid,p['example_nl'],source,f'{root.name}:{lid}:example',x['confidence'],json.dumps(metadata,ensure_ascii=False))
    await c.execute("insert into example_translations(example_id,lang,translation,source_id) values($1,'zh',$2,$3)",eid,p['example_zh'],source)
    await c.execute("update lemmas set review_status='accepted',needs_review=true,display_lemma=coalesce($2::text,display_lemma),notes=concat_ws(E'\\n',notes,$3::text),updated_at=now() where id=$1",lid,p.get('display_lemma'),p['usage_note'])
    return {'sense_id':sid,'example_id':eid,'lemma_id':lid}
async def store_expression(c,root,x,source):
    cid=int(x['target_id'].split(':')[1]);p=x['payload'];candidate=await c.fetchrow('select * from aigc_relation_candidates where id=$1 for update',cid)
    sense=await c.fetchrow('select * from senses where id=$1',p['sense_id'])
    assert sense and sense['lemma_id']==candidate['source_lemma_id'] and sense['merged_into_sense_id'] is None and sense['review_status']!='rejected'
    lid=sense['lemma_id'];pid=sense['lemma_pos_entry_id'];assert pid
    norm=unicodedata.normalize('NFC',p['expression_nl'].removesuffix('#aigc').strip().lower())
    names=['definition_nl','usage_note','gloss_en','explanation_en','gloss_zh','explanation_zh','example_nl','example_zh']
    eid=await c.fetchval('''insert into lexical_expressions(lemma_id,lemma_pos_entry_id,sense_id,entry_kind,expression_type,expression_nl,expression_norm,
      definition_nl,usage_note,gloss_en,explanation_en,gloss_zh,explanation_zh,example_nl,example_zh,source_id,external_id,confidence,raw_payload)
      values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19::jsonb) returning id''',lid,pid,p['sense_id'],p['entry_kind'],p['expression_type'],p['expression_nl'],norm,*[p[k] for k in names],source,f'{root.name}:{cid}',x['confidence'],json.dumps({'decision':x,'human_reviewed':False},ensure_ascii=False))
    await c.execute("update aigc_relation_candidates set import_status=$2,review_status=$3,raw_payload=raw_payload||jsonb_build_object('source_research',$4::jsonb),updated_at=now() where id=$1",cid,p['import_status'],'rejected' if p['entry_kind']=='usage_example' else 'needs_review',json.dumps({'run':root.name,'expression_id':eid,'decision':x},ensure_ascii=False))
    return {'expression_id':eid,'entry_kind':p['entry_kind'],'candidate_id':cid}
async def run(args):
    root=Path(args.run_dir).resolve();c=await asyncpg.connect(os.environ.get('DATABASE_URL','postgresql://postgres:postgres@127.0.0.1:54322/postgres'))
    try:
        if args.export_snapshots:
            context=json.loads((root/'context.json').read_text());ids=[f"lemma:{x['lemma']['id']}" for x in context['held_lemmas']]+[f"relation:{x['id']}" for x in context['relations']]+[f"new_sense:{x['id']}" for x in context['new_senses']]
            async with c.transaction(isolation='repeatable_read',readonly=True):data={t:await snapshot(c,t) for t in ids}
            path=root/'database-snapshots.json';assert not path.exists();path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');print(f'Exported {len(data)} native database snapshots');return
        plan=load_plan(root);snapshots=json.loads((root/'database-snapshots.json').read_text());key=digest(plan)
        if args.validate:print(json.dumps({'validated':len(plan['items']),'plan_key':key}));return
        assert (root/'before-research.dump').stat().st_size>10000
        await c.execute((ROOT/'supabase/migrations/20261023040000_researched_source_gaps.sql').read_text())
        receipts=[]
        for batch in ['A','B','C']:
            items=[x for x in plan['items'] if x['author']==batch];assert items
            async with c.transaction():
                await c.execute('select pg_advisory_xact_lock(20261023,2)')
                old=await c.fetchrow('select * from source_gap_research_batches where run_key=$1 and batch=$2',root.name,batch)
                if old:
                    assert old['plan_key']==key;receipts.append({'batch':batch,'repeat':True});continue
                source=None
                if any(x['action']!='defer' for x in items):
                    source=await c.fetchval("""insert into sources(source_key,name,source_type,version,notes) values('aigc_verified_source_research_v1','Cross-reviewed source research for residual lexical gaps','aigc_derived','2026-10-23','Source-backed model authorship and independent review; not human-approved.') on conflict(source_key) do update set updated_at=now() returning id""")
                outcomes=[]
                for x in items:
                    target=x['target_id'];before=await snapshot(c,target)
                    assert digest(before)==digest(snapshots[target]),f'Live source changed: {target}'
                    if x['action']=='restore_lemma':outcome=await restore_lemma(c,root,x,source)
                    elif x['action']=='store_expression':outcome=await store_expression(c,root,x,source)
                    else:outcome={'deferred':True}
                    after=await snapshot(c,target)
                    await c.execute('insert into source_gap_research_audit(run_key,batch,target_id,plan_key,before_state,after_state,decision) values($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7::jsonb)',root.name,batch,target,key,json.dumps(before,ensure_ascii=False),json.dumps(after,ensure_ascii=False),json.dumps({'item':x,'outcome':outcome},ensure_ascii=False))
                    outcomes.append({'target_id':target,'action':x['action'],**outcome})
                result={'batch':batch,'count':len(items),'outcomes':outcomes,'plan_key':key,'human_reviewed':False}
                await c.execute('insert into source_gap_research_batches(run_key,batch,plan_key,result) values($1,$2,$3,$4::jsonb)',root.name,batch,key,json.dumps(result,ensure_ascii=False))
            receipts.append(result)
        (root/'application-latest.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipts,ensure_ascii=False))
    finally:await c.close()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',default=str(DEFAULT));p.add_argument('--export-snapshots',action='store_true');p.add_argument('--validate',action='store_true');asyncio.run(run(p.parse_args()))
