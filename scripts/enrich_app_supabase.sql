-- Deterministic app-facing enrichment for the Dutch lexicon Supabase DB.
-- This script is idempotent and preserves source rows.

\set ON_ERROR_STOP on

begin;

update public.pos_tags
set
  app_pos = case
    when tag in ('N', 'NOUN') then 'noun'
    when tag = 'PROPN' then 'proper_noun'
    when tag in ('WW', 'VERB') then 'verb'
    when tag = 'AUX' then 'auxiliary'
    when tag in ('ADJ', 'ADJ_FROG') then 'adjective'
    when tag in ('BW', 'ADV') then 'adverb'
    when tag in ('VZ', 'ADP', 'POST') then 'adposition'
    when tag in ('VG', 'CONJ', 'SCONJ') then 'conjunction'
    when tag = 'LID' then 'article'
    when tag = 'DET' then 'determiner'
    when tag = 'VNW' or tag like 'PRON%' then 'pronoun'
    when tag in ('TW', 'NUM', 'NUM-INDEF', 'NUM-INT', 'ORDN', 'ORDN-INDEF') then 'numeral'
    when tag in ('TSW', 'INTJ') then 'interjection'
    when tag = 'PART' then 'particle'
    when tag = 'ABBR' then 'abbreviation'
    when tag = 'ADVERB-NUM' then 'adverbial_numeral'
    when tag in ('LET', 'PUNCT') then 'punctuation'
    when tag in ('SYM', 'SYMBOOL') then 'symbol'
    when tag = 'SPEC' then 'special'
    when tag = 'X' then 'unknown'
    else 'unknown'
  end,
  app_pos_label_zh = case
    when tag in ('N', 'NOUN') then '名词'
    when tag = 'PROPN' then '专有名词'
    when tag in ('WW', 'VERB') then '动词'
    when tag = 'AUX' then '助动词'
    when tag in ('ADJ', 'ADJ_FROG') then '形容词'
    when tag in ('BW', 'ADV') then '副词'
    when tag in ('VZ', 'ADP', 'POST') then '介词/后置词'
    when tag in ('VG', 'CONJ', 'SCONJ') then '连词'
    when tag = 'LID' then '冠词'
    when tag = 'DET' then '限定词'
    when tag = 'VNW' or tag like 'PRON%' then '代词'
    when tag in ('TW', 'NUM', 'NUM-INDEF', 'NUM-INT', 'ORDN', 'ORDN-INDEF') then '数词'
    when tag in ('TSW', 'INTJ') then '感叹词'
    when tag = 'PART' then '小品词'
    when tag = 'ABBR' then '缩写'
    when tag = 'ADVERB-NUM' then '数量副词'
    when tag in ('LET', 'PUNCT') then '标点'
    when tag in ('SYM', 'SYMBOOL') then '符号'
    when tag = 'SPEC' then '特殊词类'
    else '未知词类'
  end,
  app_pos_label_en = case
    when tag in ('N', 'NOUN') then 'noun'
    when tag = 'PROPN' then 'proper noun'
    when tag in ('WW', 'VERB') then 'verb'
    when tag = 'AUX' then 'auxiliary verb'
    when tag in ('ADJ', 'ADJ_FROG') then 'adjective'
    when tag in ('BW', 'ADV') then 'adverb'
    when tag in ('VZ', 'ADP', 'POST') then 'adposition'
    when tag in ('VG', 'CONJ', 'SCONJ') then 'conjunction'
    when tag = 'LID' then 'article'
    when tag = 'DET' then 'determiner'
    when tag = 'VNW' or tag like 'PRON%' then 'pronoun'
    when tag in ('TW', 'NUM', 'NUM-INDEF', 'NUM-INT', 'ORDN', 'ORDN-INDEF') then 'numeral'
    when tag in ('TSW', 'INTJ') then 'interjection'
    when tag = 'PART' then 'particle'
    when tag = 'ABBR' then 'abbreviation'
    when tag = 'ADVERB-NUM' then 'adverbial numeral'
    when tag in ('LET', 'PUNCT') then 'punctuation'
    when tag in ('SYM', 'SYMBOOL') then 'symbol'
    when tag = 'SPEC' then 'special'
    else 'unknown'
  end,
  display_order = case
    when tag in ('N', 'NOUN') then 10
    when tag = 'PROPN' then 11
    when tag in ('WW', 'VERB') then 20
    when tag = 'AUX' then 21
    when tag in ('ADJ', 'ADJ_FROG') then 30
    when tag in ('BW', 'ADV') then 40
    when tag in ('VZ', 'ADP', 'POST') then 50
    when tag in ('VG', 'CONJ', 'SCONJ') then 60
    when tag in ('LID', 'DET') then 70
    when tag = 'VNW' or tag like 'PRON%' then 80
    when tag in ('TW', 'NUM', 'NUM-INDEF', 'NUM-INT', 'ORDN', 'ORDN-INDEF', 'ADVERB-NUM') then 90
    when tag in ('TSW', 'INTJ') then 100
    when tag in ('PART', 'ABBR') then 110
    when tag in ('LET', 'PUNCT', 'SYM', 'SYMBOOL') then 900
    else 999
  end,
  is_content_pos = tag in ('N', 'NOUN', 'PROPN', 'WW', 'VERB', 'ADJ', 'ADJ_FROG', 'BW', 'ADV');

update public.forms
set
  app_form_role = case
    when is_canonical or form_type in ('canonical', 'fallback_canonical') then 'canonical'
    when form_type in ('subtlex_observed', 'cc100_observed') then 'observed_form'
    when form_type like 'odwn_%' then 'dictionary_wordform'
    else 'other_form'
  end,
  display_label_zh = case
    when is_canonical or form_type in ('canonical', 'fallback_canonical') then '标准词形'
    when form_type = 'subtlex_observed' then '字幕语料词形'
    when form_type = 'cc100_observed' then 'CC100语料词形'
    when form_type like 'odwn_%' then '词典词形'
    else '其他词形'
  end,
  display_label_en = case
    when is_canonical or form_type in ('canonical', 'fallback_canonical') then 'canonical form'
    when form_type = 'subtlex_observed' then 'SUBTLEX observed form'
    when form_type = 'cc100_observed' then 'CC100 observed form'
    when form_type like 'odwn_%' then 'dictionary word form'
    else 'other form'
  end,
  morph_features = jsonb_strip_nulls(
    jsonb_build_object(
      'source_form_type', form_type,
      'source_attributes', raw_payload -> 'attributes',
      'source_entry_id', raw_payload ->> 'entry_id'
    )
  ),
  is_observed = form_type in ('subtlex_observed', 'cc100_observed');

update public.senses
set
  display_definition_nl = nullif(btrim(definition_nl), ''),
  dedupe_key = case
    when definition_nl is null or btrim(definition_nl) = '' then null
    else regexp_replace(lower(btrim(definition_nl)), '\s+', ' ', 'g')
  end,
  merged_into_sense_id = null,
  app_sense_order = null,
  is_core = false;

with ranked_duplicates as (
  select
    s.id,
    first_value(s.id) over (
      partition by s.lemma_pos_entry_id, s.dedupe_key
      order by
        case src.source_key when 'odwn_1_3' then 1 when 'dbnary_nld_2026_05' then 2 else 9 end,
        s.is_primary desc,
        nullif(regexp_replace(coalesce(s.sense_no, ''), '[^0-9]', '', 'g'), '')::integer nulls last,
        s.id
    ) as keeper_id,
    count(*) over (partition by s.lemma_pos_entry_id, s.dedupe_key) as duplicate_count
  from public.senses s
  join public.sources src on src.id = s.source_id
  where s.dedupe_key is not null
)
update public.senses s
set merged_into_sense_id = d.keeper_id
from ranked_duplicates d
where s.id = d.id
  and d.duplicate_count > 1
  and d.id <> d.keeper_id;

with ordered_senses as (
  select
    s.id,
    row_number() over (
      partition by s.lemma_pos_entry_id
      order by
        s.is_primary desc,
        case when s.display_definition_nl is not null then 0 else 1 end,
        case src.source_key when 'odwn_1_3' then 1 when 'dbnary_nld_2026_05' then 2 else 9 end,
        nullif(regexp_replace(coalesce(s.sense_no, ''), '[^0-9]', '', 'g'), '')::integer nulls last,
        s.id
    ) as sense_order
  from public.senses s
  join public.sources src on src.id = s.source_id
  where s.merged_into_sense_id is null
)
update public.senses s
set
  app_sense_order = o.sense_order,
  is_core = o.sense_order <= 3
from ordered_senses o
where s.id = o.id;

insert into public.lemma_relations (
  lemma_id_from,
  lemma_id_to,
  relation_type,
  source_id,
  external_id,
  confidence,
  notes
)
select
  l.family_head_lemma_id,
  l.id,
  'family_member',
  src.id,
  'family:' || l.word_family || ':' || l.family_head_lemma_id || ':' || l.id,
  0.950,
  'Derived from lemmas.word_family and family_head_lemma_id.'
from public.lemmas l
join public.sources src on src.source_key = 'word_family_internal_v1'
where l.family_head_lemma_id is not null
  and l.family_head_lemma_id <> l.id
on conflict (lemma_id_from, lemma_id_to, relation_type, source_id) do update set
  confidence = excluded.confidence,
  notes = excluded.notes;

insert into public.lemma_relations (
  lemma_id_from,
  lemma_id_to,
  relation_type,
  source_id,
  external_id,
  confidence,
  notes
)
select
  l.id,
  l.family_head_lemma_id,
  'family_head',
  src.id,
  'family-head:' || l.word_family || ':' || l.id || ':' || l.family_head_lemma_id,
  0.950,
  'Derived from lemmas.word_family and family_head_lemma_id.'
from public.lemmas l
join public.sources src on src.source_key = 'word_family_internal_v1'
where l.family_head_lemma_id is not null
  and l.family_head_lemma_id <> l.id
on conflict (lemma_id_from, lemma_id_to, relation_type, source_id) do update set
  confidence = excluded.confidence,
  notes = excluded.notes;

insert into public.sense_relations (
  sense_id_from,
  sense_id_to,
  target_external_id,
  relation_type,
  source_id,
  confidence,
  notes
)
select
  s1.id,
  s2.id,
  s2.external_id,
  'same_synset',
  src.id,
  0.900,
  'Derived from shared external_synset_id.'
from public.senses s1
join public.senses s2
  on s1.external_synset_id = s2.external_synset_id
  and s1.id <> s2.id
join public.sources src on src.source_key = 'app_enrichment_rules_v1'
join (
  select external_synset_id, count(*) as sense_count
  from public.senses
  where external_synset_id is not null and btrim(external_synset_id) <> ''
  group by external_synset_id
  having count(*) between 2 and 30
) g on g.external_synset_id = s1.external_synset_id
where s1.external_synset_id is not null
  and btrim(s1.external_synset_id) <> ''
on conflict do nothing;

commit;

select 'pos_without_app_pos' as check_name, count(*) as value
from public.pos_tags
where app_pos is null
union all
select 'forms_without_app_role', count(*) from public.forms where app_form_role is null
union all
select 'senses_without_order', count(*) from public.senses where merged_into_sense_id is null and app_sense_order is null
union all
select 'lemma_relations', count(*) from public.lemma_relations
union all
select 'sense_relations', count(*) from public.sense_relations;
