# 荷兰语词典 API · 前端设计规格

合同版本：2026-10-23。以本包 `openapi.json`、`types.ts` 和实际响应为准。公网服务尚未部署，真实后端示例地址为 `http://127.0.0.1:8080`；本包回放服务为 `http://127.0.0.1:8799`。前端不接触百炼 Key，也不直接访问数据库。

## 1. 页面与请求流程

**普通查词**：输入荷兰语词头或词形 → 可选输入联想 → `/lookup` → 根据 `best_match.entry_url` 打开详情；未明确命中时展示 `did_you_mean`。点击纠错或联想候选同样使用其 `entry_url`。例如 `huizen` 会定位到 `huis`。

**按含义找词**：输入中英荷描述 → 用户提交一次 `/semantic-search` → 展示主结果卡片和独立的关联词区域 → 点击结果读取详情。主结果中的 `matched_sense.sense_id` 可用于高亮具体义项。不要把语义查询绑定到每次按键，这条链路会调用模型。

**详情**：词头信息、词性导航、三语义项、例句、词形、相关表达及来源。义项、词形、语料例句、表达各有独立分页；某一组加载下一页时，不应覆盖其他组已展示的数据。

## 2. 接口总览

| 方法与路径 | 用途 | 成功体 | 主要错误 |
| --- | --- | --- | --- |
| GET `/lookup` | 普通查词与纠错 | LookupResponse | 413 / 422 / 429 / 503 |
| GET `/suggest` | 前缀联想 | SuggestResponse | 413 / 422 / 429 / 503 |
| GET `/entries/{lemma_id}` | 完整词条的分页视图 | EntryResponse | 404 / 413 / 422 / 429 / 503 |
| GET `/senses/{sense_id}/examples` | 某义项的例句及已有译文 | SenseExamplesResponse | 404 / 413 / 422 / 429 / 503 |
| POST `/semantic-search` | 按含义找词、查询改写 | SemanticResponse | 413 / 422 / 429 / 503 |
| GET `/health` | 内部健康检查 | HealthResponse | 503；公网 Nginx 模板返回 404 |

JSON 使用 UTF-8。当前接口匿名访问，无登录或 Authorization 请求头。部署时前端宜与 API 同源，经代理转发；真实 API 目前没有配置跨域 CORS。回放服务为便于本机设计另行提供 CORS，不代表公网策略。

## 3. 请求参数

### GET /lookup

- `q`：必填字符串，1–128 字符，必须含非空白字符；服务去除首尾空格。
- `limit`：整数，默认 5，范围 1–5。
- 内存词头/词形匹配、重音及标点变体匹配优先，未命中时数据库模糊匹配。普通查询不会自动转为付费语义查询。

```http
GET /lookup?q=huizen
```

`best_match` 为对象或 null。明确命中时 `did_you_mean=[]`；没有明确命中时 `best_match=null`，纠错列表可能非空。两者都空表示当前没有候选。不得把有纠错建议误显示为已命中。

### GET /suggest

- `q`：必填字符串，1–128 字符，不能全空白。
- `limit`：默认 10，范围 1–20。
- 返回 `suggestions` 数组，允许为空，候选按词头去重。

### GET /entries/{lemma_id}

路径 ID 为正 bigint。不存在、已删除、待核或已拒绝词头统一 404。下面四组分页参数可以独立组合：

- `sense_offset=0`、`sense_limit=20`：limit 范围 1–50，offset 范围 0–10,000。
- `form_offset=0`、`form_limit=50`：limit 范围 1–100，offset 范围 0–100,000。
- `example_offset=0`、`example_limit=5`：语料例句；limit 范围 1–20，offset 范围 0–10,000。
- `expression_offset=0`、`expression_limit=20`：limit 范围 1–50，offset 范围 0–10,000。

```http
GET /entries/138
GET /entries/2327?sense_limit=7&sense_offset=7
GET /entries/1?form_offset=50
```

首次只读第一页。语义命中的义项若不在第一页，可按 `next_offset` 继续读取，直到找到对应 `sense_id`；不要假定一个词只有一个释义。

### GET /senses/{sense_id}/examples

- `sense_id`：正 bigint。
- `offset`：默认 0，范围 0–10,000。
- `limit`：默认 10，范围 1–20。
- 已拒绝、已合并义项及非 accepted 词头下的义项统一 404。

### POST /semantic-search

```json
{"query":"可以通过网址访问的一组网页","limit":10,"include_related":true}
```

- `query`：必填，1–512 字符，不能全空白。
- `limit`：默认 10，范围 1–50；部署配置若另设更低上限，会以 422 拒绝更大值。
- `include_related`：布尔值，默认 true；false 时不读取关联词。
- 直接调用 Qwen3.7-Flash 改写，再调用 text-embedding-v4 查询现有向量。没有独立意图分类步骤，也没有把检索结果再交给模型生成答案。
- 接口没有公开的 `original/rewrite` 模式参数。本包带 `-original` 的场景来自测试时关闭改写的对照组，不是前端可提交的新参数。

## 4. 响应字段说明

全部字段类型及 required/null 规则详见 `types.ts` 和 OpenAPI components；以下解释其前端含义。

### 通用候选 LookupCandidate

- `lemma_id`、`lemma`、`level`：词头标识、文字及项目分级 1–4；level 不等于 CEFR。
- `entry_url`：相对详情路径，使用同一个 API base URL 访问。
- `form_id`、`form`：命中词形，允许 null；不要用它们代替词头标题。
- `match_type`：匹配方式，例如 form_exact、lemma_exact、lemma_fuzzy、form_fuzzy；适合做辅助说明，不用于决定业务分支。
- `score`：排序分；`confidence`：0–1 的内部启发式分数，均不是校准过的概率。是否明确命中以 `best_match` 是否为 null 为准。

### 通用 Page<T>

`items` 当前页，`total` 有效总数，`offset` 本页起点，`limit` 请求页大小，`has_more` 是否仍有后续，`next_offset` 下一起点或 null。即使 offset 超过末尾，也返回 `items=[]` 和真实 total。合并页面时用各对象 ID 去重，结束条件使用 `has_more=false`。

### EntryResponse 词头与词性

- `display_lemma`：优先展示的词头形式；为空时使用 `lemma`。
- `cefr_level`、`is_academic`：现有 CEFR 标记及学术词标记；CEFR 可能为 null。
- `frequency`：当前排序采用的语料频次，不是百分比或学习人数。
- `word_family`、`family_head_lemma_id`：词族及词族中心 ID，可能为空。
- `needs_review`：来源或补充数据尚待进一步复核的标记，不应直接写作“错误”。
- `parts_of_speech`：每项有 `lemma_pos_entry_id`、源 `pos`、统一 `app_pos`、中英荷标签、`gender`、`article`、`is_primary`、`needs_review`。冠词、性别、标签允许 null。

同一个统一词性可能对应 N/NOUN 等多个来源 POS。可用 app_pos 做导航汇总，但须保留 lemma_pos_entry_id 与义项的对应关系，不能据此删除来源不同的义项。

### Sense 义项与翻译

- `sense_id`、`lemma_pos_entry_id`、`pos`、`sense_no`：标识、词性归属及源义项编号；部分字段允许 null。
- `definition_nl`：荷兰语释义；`translation_en` / `translation_zh`：优先选取的简明译义，缺失时为空字符串。
- `translations`：完整有效译义列表，含语言 `lang`、简明 `gloss`、可空 `explanation`、审核状态、置信度和来源。语言列表不应硬编码为永远只有两项。
- `usage_note`、`domain`、`register`：用法、领域、语域，允许 null。
- `app_sense_order`、`is_primary`、`is_core`：已有排序与主/核心义项标记。按接口顺序展示，不建议前端重新按翻译文字排序。
- `review_status`：accepted / needs_review / unreviewed；这些记录可以展示，但不能都标为人工终审。已拒绝和已合并义项不会返回。
- `confidence`、`source_id`：来源置信度和引用来源 ID。
- `examples`：最多三条有效义项例句预览及分页信息；更多内容从 `examples_url` 读取。此预览 limit 固定 3。

### Example 与语料例句

义项 `Example` 有 `example_id`、`sense_id`、`ex_nl`、可空 `cefr_level` 和 `quality_score`、`source_id`，以及已有 `translations`。每条译文含 `translation_id`、`example_id`、`lang`、`translation`、`source_id`。没有译文时数组为空，不会即时生成翻译。

`corpus_examples` 是另一组词头级语料例句：每项有 `lemma_example_id`、可空词性/词形 ID、`ex_nl`、质量分和来源。`sense_disambiguated=false` 明确表示尚未消歧，**不要把这些例句挂到某个具体义项下**；此表目前也没有独立译文列表。

### Form 词形

`form_id`、`lemma_pos_entry_id`、`form`、`form_type`、`app_form_role`、中英展示标签、`morph_features`、`is_canonical`、`is_observed`、`needs_review`、`confidence`、`source_id`。`morph_features` 是开放 JSON 对象，不能假定所有词形都有固定的时态/单复数字段。停用的错误关联不会返回。

### Expression 表达及说明

`entry_kind` 区分 lexical_expression（词汇表达）、usage_construction（语法构式）、definition_note（释义说明）、usage_example（用例）。可按此设计四类区块，**不能统一称为固定搭配**。

每项还包含 expression_id、关联词性/义项 ID、expression_type、expression_nl、definition_nl、usage_note、英中 gloss/explanation、example_nl/example_zh、review_status、confidence、source_id。审核状态保留，拒绝记录不会返回。

### Source 来源

`sources` 是当前响应引用的去重来源列表。每项含 source_id、source_key、name、source_type、url、license、license_url、attribution、version。通过 source_id 关联，链接/许可证/署名/版本允许为空。详情展示保留适当来源和署名入口；不把所有数据标作项目原创。正文导入标记 `#aigc` 已在展示层去除，原来源和审核状态仍保留。

### SemanticResponse 语义结果

- `query` 是原输入；`language` 当前固定 unknown，不能当作检测结果。
- `results` 是主结果数组，每项含词头、entry_url、分级、score、matched_sense 和 matched_reason。
- `matched_sense` 有 sense_id、荷英中简明释义及 semantic_score（原始向量相似度）。
- `matched_reason` 包括 semantic_score、frequency_boost、level_boost；最终 score 是加权排序分，可能超过 1，**不要显示为“准确率百分比”**。
- `related_results` 独立列出关系扩展结果：lemma_id、lemma、entry_url、relation_type、source_result_lemma_id、可空 source_result_sense_id、source、score。不要把它们混成同等语义命中。
- `query_rewrite`：实际用于检索的 query、status、model、prompt_version。rewritten 表示改写，unchanged 表示调用后保留原文；其他状态为关闭、未配置或回退原因。完整状态枚举见类型文件。

可在用户需要时显示“用于搜索的描述”，并允许看到原文；默认界面不必展示供应商、预算账本等服务实现信息。回退成功时仍正常展示结果，可用简短提示“已按原描述搜索”。

接口当前没有低相关性拒答阈值；无关或恶意输入也可能返回最相近的词。不要仅凭 results 非空声称输入一定与词库有关，也不能把模型输出当成执行指令。用户输入和数据库文本均按纯文本转义显示。

词性、否定等限制目前作为检索文本参与向量匹配，没有硬性词性过滤或逻辑求解保证。卡片可能仍出现不满足限制的结果，须通过匹配义项和详情核对。结果列表不宜为每张卡片预加载全部详情，以免很快用完共享查询额度。

## 5. 限流、错误和页面状态

全部公开查词/详情/例句端点共享单 IP 60 次/分钟、10 秒最多 10 次；语义另限 10 次/分钟。404/422 也计入应用额度。代理头由可信代理处理，浏览器不发送 X-Forwarded-For。当前限流存储只适用于单进程服务；前端不能通过重复创建请求来获得新额度。

- 200 + 空数组/null：正常空态。普通查词先区分纠错建议，再显示没有匹配。
- 404：词条或义项不存在/不显示，提供返回搜索入口。
- 413：请求体超过 8 KiB，提示缩短输入。
- 422：参数不合法。`detail` 通常为校验错误数组，含 loc/msg/type，可能含 input/ctx；配置结果数上限错误也可能是字符串。
- 429：暂停提交，优先使用 Retry-After 秒数做倒计时。应用返回 JSON detail；Nginx 也可能返回 HTML 且不带该头，先判断状态码和 Content-Type，不应直接无条件 response.json()。
- 503：服务、数据库、模型或预算暂不可用，或语义功能未开启。提示稍后重试，并允许使用普通查词；不用供应商错误堆栈填充页面。

不建议自动重试语义查询，取消浏览器等待也不保证已发出的模型请求不计费。输入联想建议防抖、缓存重复前缀并丢弃过时响应；实际防抖时间可按共享 IP 限额调整。普通搜索与语义搜索采用显式模式切换，当前没有自动意图分流接口。

## 6. Mock 场景来源与使用

`mock/manifest.json` 列出每个场景的真实请求、状态、响应文件、耗时和 provenance。`actual_api_real_models` 为真实 Flash/v4 和数据库；`actual_api_database` 为真实词库只读请求；带 injected 的场景是在模型故障注入后，由真实接口使用原文与真实 v4 生成的响应，不代表供应商实际发生故障。原始 JSON 响应不为页面效果编造或改写。

`X-Mock-Scenario` 是本包回放服务专用头，不是生产 API 参数。使用它可强制选择 404/429/503、超时回退、分页等场景。同一个请求的 original/rewrite 对照响应同时保留；默认回放优先选择最终 rewrite 场景。未录制请求返回 mock 专用 501，不能将其视为生产 API 错误合同。

具体测试规模、成本、延迟、改写质量与限制见 `reports/真实查询验证报告.md`。小样本只用于本轮验收，不能当作全库准确率或生产吞吐量承诺。
