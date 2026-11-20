#!/usr/bin/env python3
"""Apply a pinned human-review manifest with optimistic checks and full audit images.

No inferred merges, paid API calls or hard deletes. A repeated identical manifest is
idempotent. Corrections supersede translations; source text is retained in audit.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lexicon_search.quality import translation_blockers

ALLOWED = {'senses': {'usage_note', 'display_definition_nl'}, 'examples': {'ex_nl'}}


def validate_action(action):
    if not action.get('evidence'):
        raise ValueError('Missing review evidence')
    if action['table'] == 'sense_translations':
        if set(action['values']) != {'gloss', 'explanation'}:
            raise ValueError('Translation requires both text fields')
        if action.get('decision') not in {'human_verbatim', 'review_guided'}:
            raise ValueError('Missing human/assisted distinction')
        if any(not isinstance(v,str) or not v.strip() for v in action['values'].values()):
            raise ValueError('Empty translation')
        if translation_blockers(action['expected']['lang'], **action['values']):
            raise ValueError('Corrupt translation')
    elif action['table'] not in ALLOWED or not set(action['values']) <= ALLOWED[action['table']]:
        raise ValueError('Unsupported mutation')
    if not action['expected'] or type(action['id']) is not int:
        raise ValueError('Missing snapshot precondition')


def assert_expected(before, expected):
    if before is None or any(before.get(k) != v for k,v in expected.items()):
        raise ValueError('Live record changed; regenerate and review the manifest')


async def apply(manifest_path, apply_changes=False):
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    fingerprint = hashlib.sha256(raw).hexdigest()
    actions = manifest['actions']
    keys = [f"{a['table']}:{a['id']}" for a in actions]
    if len(set(keys)) != len(keys):
        raise ValueError('Multiple actions for the same row')
    for a in actions:
        validate_action(a)
    conn = await asyncpg.connect(os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@127.0.0.1:54322/postgres'))
    try:
        async with conn.transaction():
            await conn.execute('select pg_advisory_xact_lock(20261031, 1)')
            exists = await conn.fetchval("select to_regclass('public.human_review_audit')")
            previous = await conn.fetch('select manifest_hash from human_review_audit where run_key=$1',manifest['run_key']) if exists else []
            if previous:
                if len(previous) != len(actions) or any(r['manifest_hash'] != fingerprint for r in previous):
                    raise ValueError('Run key already used with a different manifest')
                return {'repeat': True, 'actions': len(actions)}
            before_rows = []
            for a in actions:
                table = a['table']
                encoded = await conn.fetchval(f'select to_jsonb(t) from public.{table} t where id=$1 for update',a['id'])
                before = json.loads(encoded) if encoded else None
                assert_expected(before,a['expected'])
                before_rows.append(before)
            dirty = sorted({b['sense_id'] for a,b in zip(actions,before_rows) if a['table']=='sense_translations'} |
                           {a['id'] for a in actions if a['table']=='senses' and 'display_definition_nl' in a['values']})
            vectors = [dict(r) for r in await conn.fetch('select sense_id, embedding_model, embedding_dim, index_version from sense_embeddings where sense_id=any($1::bigint[])',dirty)]
            backup = {'run_key':manifest['run_key'],'manifest_hash':fingerprint,'rows':before_rows,'embedding_metadata':vectors}
            backup_path = manifest_path.with_suffix('.backup.json')
            if backup_path.exists() and json.loads(backup_path.read_text()) != backup:
                raise ValueError('Existing backup differs; refusing to overwrite')
            backup_path.write_text(json.dumps(backup,ensure_ascii=False,indent=2)+'\n')
            if not apply_changes:
                return {'dry_run':True,'actions':len(actions),'dirty_senses':len(dirty),'backup':str(backup_path)}
            await conn.execute((ROOT/'supabase/migrations/20261031090000_human_review_audit.sql').read_text())
            source_id = await conn.fetchval("""insert into sources(source_key,name,source_type,url,version,notes)
                values($2,'Human review with individually recorded assisted corrections','human_review',
                $1,'2026-10-31','Verbatim human corrections are accepted; assistant-normalized wording remains needs_review. See private human_review_audit.')
                on conflict(source_key) do update set notes=excluded.notes returning id""",manifest['document_url'],
                'human_review:'+manifest['run_key'])
            new_translations = 0
            for a,before,key in zip(actions,before_rows,keys):
                provenance = {'run_key':manifest['run_key'],'manifest_hash':fingerprint,'evidence':a['evidence'],
                              'decision':a.get('decision','mechanical_cleanup'),'original_row_id':a['id']}
                if a['table']=='sense_translations':
                    human = a['decision']=='human_verbatim'
                    suffix = '' if human else '#aigc'
                    new_id = await conn.fetchval("""insert into sense_translations
                        (sense_id,lang,gloss,explanation,source_id,external_id,confidence,review_status,translation_style,raw_payload)
                        values($1,$2,$3,$4,$5,$6,$7,$8,'learner_dictionary',$9::jsonb) returning id""",
                        before['sense_id'],before['lang'],a['values']['gloss']+suffix,a['values']['explanation']+suffix,
                        source_id,f"{manifest['run_key']}:{a['id']}",.95 if human else .85,
                        'accepted' if human else 'needs_review',json.dumps(provenance,ensure_ascii=False))
                    await conn.execute("update sense_translations set review_status='rejected',updated_at=now() where id=$1",a['id'])
                    new_translations += 1
                    after = {'superseded_id':a['id'],'replacement':json.loads(await conn.fetchval('select to_jsonb(t) from sense_translations t where id=$1',new_id))}
                else:
                    table = a['table']
                    fields = list(a['values'])
                    assignments = ','.join(f'{k}=${i+2}' for i,k in enumerate(fields))
                    payload = before.get('raw_payload')
                    payload = dict(payload) if isinstance(payload,dict) else {'original_payload':payload}
                    payload.setdefault('human_review_history',[]).append(provenance)
                    if 'usage_note' in a['values'] and before.get('usage_note'):
                        payload.setdefault('internal_editorial_notes',[]).append(before['usage_note'])
                    await conn.execute(f'update {table} set {assignments},raw_payload=${len(fields)+2}::jsonb,updated_at=now() where id=$1',
                                       a['id'],*[a['values'][k] for k in fields],json.dumps(payload,ensure_ascii=False))
                    after = json.loads(await conn.fetchval(f'select to_jsonb(t) from {table} t where id=$1',a['id']))
                await conn.execute('insert into human_review_audit(run_key,action_key,manifest_hash,proposal,before_state,after_state) values($1,$2,$3,$4::jsonb,$5::jsonb,$6::jsonb)',
                                   manifest['run_key'],key,fingerprint,json.dumps(a,ensure_ascii=False),json.dumps(before,ensure_ascii=False),json.dumps(after,ensure_ascii=False))
            # Preserve vectors but exclude obsolete text from the active semantic index.
            await conn.execute("update sense_embeddings set index_version=$2,updated_at=now() where sense_id=any($1::bigint[])",dirty,'stale:'+manifest['run_key'])
            return {'applied':True,'actions':len(actions),'new_translations':new_translations,'dirty_senses':len(dirty),
                    'invalidated_vectors':len(vectors),'backup':str(backup_path)}
    finally:
        await conn.close()


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('manifest',type=Path)
    p.add_argument('--apply',action='store_true')
    a=p.parse_args()
    print(json.dumps(asyncio.run(apply(a.manifest,a.apply)),ensure_ascii=False,indent=2))
