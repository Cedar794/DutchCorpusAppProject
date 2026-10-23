# 词条详情 API

## 普通查词到详情

先请求 `GET /lookup?q=huizen`，命中结果的 `best_match` 返回 `lemma_id=138`、`lemma=huis` 和 `entry_url=/entries/138`。再请求该地址读取词条。纠错建议、输入联想、语义结果和关联词同样带有 `entry_url`；原有字段保留。

```bash
curl --fail 'http://127.0.0.1:8080/lookup?q=huizen'
curl --fail 'http://127.0.0.1:8080/entries/138'
```

这两步只读取现有词库，不调用翻译、改写或 embedding 模型。语义反查仍是独立入口，默认关闭。当前仓库尚无对接这些接口的前端页面。

## GET /entries/{lemma_id}

只返回 `review_status=accepted` 的词头。不存在、已删除、待核或已拒绝词头统一返回 404。ID 必须为正 bigint。

返回词头、展示形式、分级、CEFR、词频、学术词标记、词族及以下内容：

- `parts_of_speech`：词性、荷英中标签、冠词、性别、主词性和待核标记。
- `senses`：未合并、未拒绝的义项；含荷兰语释义、用法、领域、语域、审核状态、置信度、来源，以及英中便捷译义和完整 `translations`。
- `forms`：有效词形、词形角色、展示标签、形态特征、规范/实际观察标记和来源。
- `corpus_examples`：词头层面语料例句。`sense_disambiguated=false`，不可当作某个义项的已消歧例句；目前此类例句没有独立译文表。
- `expressions`：多词表达、语法构式、释义说明及用例；保留 `entry_kind`，不可将所有记录都标成固定搭配。含现有荷英中内容、例句、审核状态与来源；已拒绝记录及关联无效义项的记录被过滤。
- `sources`：当前响应引用的来源 ID、名称、类型、链接、许可证、署名与版本。各内容以 `source_id` 引用；不返回原始导入载荷、内部审计或归档。

内容中的尾缀 `#aigc` 只在展示时移除，数据库原文保留；来源、审核状态和置信度仍返回，不能据此认为内容已经人工终审。译义数组只包含非空、未拒绝记录；同一语言有多个版本时，便捷字段依次优先 accepted、needs_review、unreviewed，再比较置信度和记录 ID。完整数组保留这些版本及状态。

### 分页

`senses`、`forms`、`corpus_examples` 和 `expressions` 均返回 `items`、`total`、`offset`、`limit`、`has_more`、`next_offset`。空页仍返回完整总数。需要全部内容时，客户端根据 `next_offset` 继续请求，不应把第一页当作完整词条。

- 义项：`sense_offset=0`、`sense_limit=20`，最多 50 条，offset 上限 10,000。
- 词形：`form_offset=0`、`form_limit=50`，最多 100 条，offset 上限 100,000。
- 语料例句：`example_offset=0`、`example_limit=5`，最多 20 条，offset 上限 10,000。
- 表达：`expression_offset=0`、`expression_limit=20`，最多 50 条，offset 上限 10,000。

```bash
curl --fail 'http://127.0.0.1:8080/entries/2327?sense_limit=7&sense_offset=7'
```

每个义项附最多 3 条有效例句预览，含已有译文、来源、总数和 `examples_url`。预览的 `has_more=true` 时可通过下一接口读取余下例句。

## GET /senses/{sense_id}/examples

返回所属 `lemma_id`、`entry_url`、例句分页与来源列表。`offset` 默认 0、上限 10,000；`limit` 默认 10、最多 20。仅返回有效例句和非空已有译文；不为缺失译文自动生成内容。已拒绝、已合并义项或非 accepted 词头下的义项统一返回 404。

```bash
curl --fail 'http://127.0.0.1:8080/senses/实际义项ID/examples?offset=3&limit=10'
```

## 限流与错误

两个新端点共享现有单 IP 总额度：60 次/分钟、10 次/10 秒；语义查询另限 10 次/分钟。详情、例句、普通查词和联想互相计数，404/422 请求也计数。客户端伪造 `X-Forwarded-For` 不能绕过应用限流。超限 429 并返回 `Retry-After`；数据库暂不可用时返回不含内部信息的 503，参数越界返回 422。

数据读取使用只读、可重复读事务，确保单次响应的分页、总数和译文来自同一数据库快照。API 不支持批量 ID 查询或词库导出。词头定位仍使用启动时的内存索引；详情从数据库实时读取，完整词库更新后仍需重载匹配索引。

## 部署与验证

新版本上线前应用 `supabase/migrations/20261023060000_entry_detail_indexes.sql`，为例句译文增加按 example_id 查询的索引；并重新执行 `deploy/search-db-permissions.sql`，补齐来源、词性及例句表的只读权限。Nginx 模板已放行两个新端点并复用边缘限流。现有数据库还需具备此前的词形隔离和 lexical_expressions 迁移。

自动测试：

```bash
.venv/bin/python -m unittest discover -s tests
# 对受控本地数据库设置 SEARCH_TEST_DATABASE_URL 后运行集成测试。
# 集成测试在事务中构造夹具并回滚，部署权限检查的角色/策略变更也回滚。
.venv/bin/python -m unittest tests.test_entry_details -v
```

2026-10-23 已完成 115 项测试（含 4 项 PostgreSQL 集成测试）；另外对 11 个实际词条及 33 义项分页、停用词形、已删除词头、已拒绝义项、默认共享突发限额做了 ASGI/数据库检查。实际响应样本和回执保存在 `outputs/entry_details_20261023`。这些是本机功能检查，不代表公网负载容量；本次没有调用付费模型。
