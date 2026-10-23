#!/usr/bin/env python3
"""Check queue dispositions and live records after independently reviewed bilingual repair."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
import asyncpg
try:
    from .repair_bilingual_gaps import prepare,rows
except ImportError:
    from repair_bilingual_gaps import prepare,rows

async def audit(root,require_finished=False):
    root=root.resolve()
    manifest=json.loads((root/'manifest.json').read_text());authored=reviewed=0;finals={};committed=[]
    for job in manifest:
        if (root/'ready'/f"author-{job['author']}-{job['chunk']}.json").exists():authored+=job['count']
        if not (root/'reviews'/f"review-{job['reviewer']}-{job['chunk']}.json").exists():continue
        final,provenance=prepare(root,job);reviewed+=len(final)
        for row in final:
            if row['sense_id'] in finals:raise ValueError('Duplicate primary disposition')
            finals[row['sense_id']]=row
        receipt=root/'imports'/f"{job['chunk']}.done.json"
        if receipt.exists():
            data=json.loads(receipt.read_text());assert data['provenance']==provenance;committed.append(data)
    c=await asyncpg.connect('postgresql://postgres:postgres@127.0.0.1:54322/postgres')
    try:
        async with c.transaction(isolation='repeatable_read',readonly=True):
            queue=rows(root/'queue.jsonl');ids=[x['sense_id'] for x in queue]
            live=[dict(x) for x in await c.fetch('''select s.id sense_id,s.review_status,l.lemma,
              coalesce(s.display_definition_nl,s.definition_nl) definition_nl,
              coalesce((select jsonb_agg(to_jsonb(t) order by t.id) from sense_translations t
                where t.sense_id=s.id and t.lang in ('en','zh') and t.review_status<>'rejected'),'[]') active_translations,
              (select a.proposal from english_source_repair_audit a where a.sense_id=s.id
                and a.created_at>=$3::text::timestamptz order by a.id desc limit 1) source_proposal,
              exists(select 1 from sense_translations t where t.sense_id=s.id and lang='zh' and review_status<>'rejected' and btrim(gloss)<>'') has_zh,
              exists(select 1 from sense_translations t where t.sense_id=s.id and lang='en' and review_status<>'rejected' and btrim(gloss)<>'') has_en,
              exists(select 1 from bilingual_gap_repair_audit a where a.run_key=$2 and a.sense_id=s.id) audited,
              exists(select 1 from english_source_repair_audit a where a.sense_id=s.id and a.created_at>=$3::text::timestamptz) repaired_source
              from senses s join lemmas l on l.id=s.lemma_id where s.id=any($1::bigint[])''',ids,root.name,'2026-10-23T00:00:00Z')]
            blocked=[x for x in live if finals.get(x['sense_id'],{}).get('decision')=='blocked' and not x['repaired_source']]
            mismatches=[]
            committed_ids={x['sense_id'] for batch in committed for x in batch['outcomes']}
            snapshots={x['sense_id']:x for x in queue}
            for row in live:
                sid=row['sense_id'];decision=finals.get(sid)
                if not decision or sid not in committed_ids:continue
                translations=json.loads(row['active_translations'])
                proposal=json.loads(row['source_proposal']) if row['source_proposal'] else None
                if proposal:
                    if proposal['action']=='reject_mapping':
                        if row['review_status']!='rejected':mismatches.append({'sense_id':sid,'reason':'source rejection not effective'})
                        continue
                    expected={'en':proposal['gloss_en'],'zh':proposal['gloss_zh']}
                    if row['definition_nl']!=proposal['definition_nl']:
                        mismatches.append({'sense_id':sid,'reason':'source definition differs from supplemental review'})
                elif decision['decision']=='correct':
                    expected={lang:decision['translations'][lang]['gloss'] for lang in ['en','zh']}
                elif decision['decision']=='keep':
                    expected={t['lang']:t['gloss'] for t in snapshots[sid]['translations']
                              if t['lang'] in ['en','zh'] and t['review_status']!='rejected'}
                else:continue
                for lang,gloss in expected.items():
                    matching=[t for t in translations if t['lang']==lang and t['gloss']==gloss]
                    if not matching:mismatches.append({'sense_id':sid,'lang':lang,'reason':'live gloss differs from final reviewed text'})
                    if not proposal and decision['decision']=='correct' and matching:
                        pair=decision['translations'][lang]
                        if not any(t['explanation']==pair['explanation'] for t in matching):
                            mismatches.append({'sense_id':sid,'lang':lang,'reason':'live explanation differs from final reviewed text'})
            counts=dict(await c.fetchrow('''select count(*) total_senses,
              count(*) filter(where merged_into_sense_id is null and s.review_status<>'rejected') active_senses,
              count(*) filter(where merged_into_sense_id is null and s.review_status<>'rejected' and not exists(select 1 from sense_translations t where t.sense_id=s.id and lang='en' and t.review_status<>'rejected' and btrim(gloss)<>'')) missing_en,
              count(*) filter(where merged_into_sense_id is null and s.review_status<>'rejected' and not exists(select 1 from sense_translations t where t.sense_id=s.id and lang='zh' and t.review_status<>'rejected' and btrim(gloss)<>'')) missing_zh from senses s'''))
            generated=dict(await c.fetchrow('''select count(*) translation_rows,
              count(*) filter(where t.review_status='needs_review') needs_review,
              count(*) filter(where right(gloss,5)<>'#aigc' or right(explanation,5)<>'#aigc') missing_markers from sense_translations t join sources src on src.id=t.source_id where src.source_key='aigc_bilingual_gap_repair_v1' '''))
            embeddings=await c.fetchval('select count(*) from sense_embeddings')
            lemma_statuses=[dict(x) for x in await c.fetch('select review_status,count(*) n from lemmas group by review_status')]
            empty_accepted=await c.fetchval("select count(*) from lemmas l where review_status='accepted' and not exists(select 1 from senses s where s.lemma_id=l.id and s.review_status<>'rejected' and s.merged_into_sense_id is null)")
    finally:await c.close()
    result={'audited_at':datetime.now(timezone.utc).isoformat(),'queue_total':len(ids),'authored':authored,'independently_reviewed':reviewed,
      'committed_chunks':len(committed),'committed_rows':sum(x['count'] for x in committed),
      'primary_decisions':dict(Counter(x['decision'] for x in finals.values())),
      'source_blocked_still_unresolved':blocked,'live_content_mismatches':mismatches,'database':counts,'generated':generated,
      'empty_accepted_lemmas':empty_accepted,'lemma_statuses':lemma_statuses,'embeddings':embeddings,'human_reviewed':False}
    if require_finished:
        assert authored==reviewed==len(ids) and len(committed)==len(manifest)
        assert not blocked and not mismatches and all(x['audited'] or x['repaired_source'] for x in live)
        assert counts['missing_en']==counts['missing_zh']==0 and empty_accepted==0
        assert embeddings==0 and generated['missing_markers']==0
    (root/'completion-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',default='outputs/gap_repair_20261023');p.add_argument('--require-finished',action='store_true');a=p.parse_args();asyncio.run(audit(Path(a.run_dir),a.require_finished))
