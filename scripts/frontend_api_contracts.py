"""Frontend response contracts used to export and validate the handoff fixtures.

These models describe the current wire format. They do not alter API responses.
"""
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


Level = Literal[1,2,3,4]
Review = Literal['accepted','needs_review','unreviewed']
T = TypeVar('T')


class Page(Contract, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    has_more: bool
    next_offset: int | None


class LookupCandidate(Contract):
    lemma_id: int
    entry_url: str
    lemma: str
    level: Level | None
    form_id: int | None
    form: str | None
    match_type: str
    score: float
    confidence: float = Field(ge=0,le=1)


class LookupResponse(Contract):
    query: str
    mode: Literal['lookup']
    best_match: LookupCandidate | None
    did_you_mean: list[LookupCandidate]


class SuggestResponse(Contract):
    query: str
    mode: Literal['suggest']
    suggestions: list[LookupCandidate]


class Source(Contract):
    source_id: int
    source_key: str
    name: str
    source_type: str
    url: str | None
    license: str | None
    license_url: str | None
    attribution: str | None
    version: str | None


class PartOfSpeech(Contract):
    lemma_pos_entry_id: int
    pos: str
    app_pos: str | None
    label_zh: str | None
    label_en: str | None
    label_nl: str | None
    gender: str | None
    article: str | None
    is_primary: bool
    needs_review: bool


class SenseTranslation(Contract):
    translation_id: int
    sense_id: int
    lang: str
    gloss: str
    explanation: str | None
    review_status: Review
    confidence: float = Field(ge=0,le=1)
    source_id: int | None


class ExampleTranslation(Contract):
    translation_id: int
    example_id: int
    lang: str
    translation: str
    source_id: int | None


class Example(Contract):
    example_id: int
    sense_id: int
    ex_nl: str
    cefr_level: str | None
    quality_score: float | None
    source_id: int | None
    translations: list[ExampleTranslation]


class Sense(Contract):
    sense_id: int
    lemma_pos_entry_id: int | None
    pos: str | None
    sense_no: str | None
    definition_nl: str
    usage_note: str | None
    domain: str | None
    register_: str | None = Field(alias='register')
    is_primary: bool
    is_core: bool
    app_sense_order: int | None
    review_status: Review
    confidence: float = Field(ge=0,le=1)
    source_id: int
    translations: list[SenseTranslation]
    translation_zh: str
    translation_en: str
    examples: Page[Example]
    examples_url: str


class Form(Contract):
    form_id: int
    lemma_pos_entry_id: int | None
    form: str
    form_type: str | None
    app_form_role: str | None
    display_label_zh: str | None
    display_label_en: str | None
    morph_features: dict[str,Any]
    is_canonical: bool
    is_observed: bool
    needs_review: bool
    confidence: float = Field(ge=0,le=1)
    source_id: int | None


class CorpusExample(Contract):
    lemma_example_id: int
    lemma_pos_entry_id: int | None
    form_id: int | None
    ex_nl: str
    quality_score: float | None
    source_id: int | None


class CorpusExamplesPage(Page[CorpusExample]):
    sense_disambiguated: Literal[False]


class Expression(Contract):
    expression_id: int
    lemma_pos_entry_id: int
    sense_id: int
    entry_kind: Literal['lexical_expression','usage_construction','definition_note','usage_example']
    expression_type: str
    expression_nl: str
    definition_nl: str
    usage_note: str
    gloss_en: str
    explanation_en: str
    gloss_zh: str
    explanation_zh: str
    example_nl: str
    example_zh: str
    review_status: Literal['accepted','needs_review']
    confidence: float = Field(ge=0,le=.9)
    source_id: int


class EntryResponse(Contract):
    lemma_id: int
    lemma: str
    display_lemma: str | None
    level: Level
    cefr_level: str | None
    is_academic: bool
    word_family: str | None
    family_head_lemma_id: int | None
    needs_review: bool
    source_id: int | None
    frequency: int
    entry_url: str
    parts_of_speech: list[PartOfSpeech]
    senses: Page[Sense]
    forms: Page[Form]
    corpus_examples: CorpusExamplesPage
    expressions: Page[Expression]
    sources: list[Source]


class SenseExamplesResponse(Contract):
    sense_id: int
    lemma_id: int
    entry_url: str
    examples: Page[Example]
    sources: list[Source]


class QueryRewrite(Contract):
    query: str
    status: Literal['rewritten','unchanged','disabled','unconfigured','timeout','provider_error',
                    'circuit_open','busy','budget_unavailable','invalid_or_unavailable','constraint_fallback']
    model: Literal['qwen3.7-flash'] | None
    prompt_version: str | None


class MatchedSense(Contract):
    sense_id: int
    definition_nl: str
    translation_zh: str
    translation_en: str
    semantic_score: float


class SemanticResult(Contract):
    lemma_id: int
    entry_url: str
    lemma: str
    level: Level | None
    score: float
    matched_sense: MatchedSense
    matched_reason: dict[str,float]


class RelatedResult(Contract):
    lemma_id: int
    lemma: str
    entry_url: str
    relation_type: str
    source_result_lemma_id: int
    source_result_sense_id: int | None
    source: str
    score: float


class SemanticResponse(Contract):
    query: str
    language: Literal['unknown']
    results: list[SemanticResult]
    related_results: list[RelatedResult]
    query_rewrite: QueryRewrite


class HealthResponse(Contract):
    status: Literal['ok']


class ErrorResponse(Contract):
    detail: str


RESPONSES = {'/lookup':LookupResponse,'/suggest':SuggestResponse,'/entries/{lemma_id}':EntryResponse,
             '/senses/{sense_id}/examples':SenseExamplesResponse,'/semantic-search':SemanticResponse,
             '/health':HealthResponse}
