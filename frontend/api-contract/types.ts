// Generated from openapi.json. IDs are JSON integers; current IDs fit JavaScript safe integers.

export interface CorpusExample {
  lemma_example_id: number;
  lemma_pos_entry_id: number | null;
  form_id: number | null;
  ex_nl: string;
  quality_score: number | null;
  source_id: number | null;
}

export interface CorpusExamplesPage {
  items: Array<CorpusExample>;
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  next_offset: number | null;
  sense_disambiguated: false;
}

export interface EntryResponse {
  lemma_id: number;
  lemma: string;
  display_lemma: string | null;
  level: 1 | 2 | 3 | 4;
  cefr_level: string | null;
  is_academic: boolean;
  word_family: string | null;
  family_head_lemma_id: number | null;
  needs_review: boolean;
  source_id: number | null;
  frequency: number;
  entry_url: string;
  parts_of_speech: Array<PartOfSpeech>;
  senses: Page_Sense_;
  forms: Page_Form_;
  corpus_examples: CorpusExamplesPage;
  expressions: Page_Expression_;
  sources: Array<Source>;
}

export interface ErrorResponse {
  detail: string;
}

export interface Example {
  example_id: number;
  sense_id: number;
  ex_nl: string;
  cefr_level: string | null;
  quality_score: number | null;
  source_id: number | null;
  translations: Array<ExampleTranslation>;
}

export interface ExampleTranslation {
  translation_id: number;
  example_id: number;
  lang: string;
  translation: string;
  source_id: number | null;
}

export interface Expression {
  expression_id: number;
  lemma_pos_entry_id: number;
  sense_id: number;
  entry_kind: "lexical_expression" | "usage_construction" | "definition_note" | "usage_example";
  expression_type: string;
  expression_nl: string;
  definition_nl: string;
  usage_note: string;
  gloss_en: string;
  explanation_en: string;
  gloss_zh: string;
  explanation_zh: string;
  example_nl: string;
  example_zh: string;
  review_status: "accepted" | "needs_review";
  confidence: number;
  source_id: number;
}

export interface Form {
  form_id: number;
  lemma_pos_entry_id: number | null;
  form: string;
  form_type: string | null;
  app_form_role: string | null;
  display_label_zh: string | null;
  display_label_en: string | null;
  morph_features: Record<string, unknown>;
  is_canonical: boolean;
  is_observed: boolean;
  needs_review: boolean;
  confidence: number;
  source_id: number | null;
}

export interface HTTPValidationError {
  detail?: Array<ValidationError>;
}

export interface HealthResponse {
  status: "ok";
}

export interface LookupCandidate {
  lemma_id: number;
  entry_url: string;
  lemma: string;
  level: 1 | 2 | 3 | 4 | null;
  form_id: number | null;
  form: string | null;
  match_type: string;
  score: number;
  confidence: number;
}

export interface LookupResponse {
  query: string;
  mode: "lookup";
  best_match: LookupCandidate | null;
  did_you_mean: Array<LookupCandidate>;
}

export interface MatchedSense {
  sense_id: number;
  definition_nl: string;
  translation_zh: string;
  translation_en: string;
  semantic_score: number;
}

export interface Page_Example_ {
  items: Array<Example>;
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  next_offset: number | null;
}

export interface Page_Expression_ {
  items: Array<Expression>;
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  next_offset: number | null;
}

export interface Page_Form_ {
  items: Array<Form>;
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  next_offset: number | null;
}

export interface Page_Sense_ {
  items: Array<Sense>;
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  next_offset: number | null;
}

export interface PartOfSpeech {
  lemma_pos_entry_id: number;
  pos: string;
  app_pos: string | null;
  label_zh: string | null;
  label_en: string | null;
  label_nl: string | null;
  gender: string | null;
  article: string | null;
  is_primary: boolean;
  needs_review: boolean;
}

export interface QueryRewrite {
  query: string;
  status: "rewritten" | "unchanged" | "disabled" | "unconfigured" | "timeout" | "provider_error" | "circuit_open" | "busy" | "budget_unavailable" | "invalid_or_unavailable" | "constraint_fallback";
  model: "qwen3.7-flash" | null;
  prompt_version: string | null;
}

export interface RelatedResult {
  lemma_id: number;
  lemma: string;
  entry_url: string;
  relation_type: string;
  source_result_lemma_id: number;
  source_result_sense_id: number | null;
  source: string;
  score: number;
}

export interface SemanticResponse {
  query: string;
  language: "unknown";
  results: Array<SemanticResult>;
  related_results: Array<RelatedResult>;
  query_rewrite: QueryRewrite;
}

export interface SemanticResult {
  lemma_id: number;
  entry_url: string;
  lemma: string;
  level: 1 | 2 | 3 | 4 | null;
  score: number;
  matched_sense: MatchedSense;
  matched_reason: Record<string, number>;
}

export interface SemanticSearchRequest {
  query: string;
  limit?: number;
  include_related?: boolean;
}

export interface Sense {
  sense_id: number;
  lemma_pos_entry_id: number | null;
  pos: string | null;
  sense_no: string | null;
  definition_nl: string;
  usage_note: string | null;
  domain: string | null;
  register: string | null;
  is_primary: boolean;
  is_core: boolean;
  app_sense_order: number | null;
  review_status: "accepted" | "needs_review" | "unreviewed";
  confidence: number;
  source_id: number;
  translations: Array<SenseTranslation>;
  translation_zh: string;
  translation_en: string;
  examples: Page_Example_;
  examples_url: string;
}

export interface SenseExamplesResponse {
  sense_id: number;
  lemma_id: number;
  entry_url: string;
  examples: Page_Example_;
  sources: Array<Source>;
}

export interface SenseTranslation {
  translation_id: number;
  sense_id: number;
  lang: string;
  gloss: string;
  explanation: string | null;
  review_status: "accepted" | "needs_review" | "unreviewed";
  confidence: number;
  source_id: number | null;
}

export interface Source {
  source_id: number;
  source_key: string;
  name: string;
  source_type: string;
  url: string | null;
  license: string | null;
  license_url: string | null;
  attribution: string | null;
  version: string | null;
}

export interface SuggestResponse {
  query: string;
  mode: "suggest";
  suggestions: Array<LookupCandidate>;
}

export interface ValidationError {
  loc: Array<string | number>;
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}
