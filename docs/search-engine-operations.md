# 查词服务部署与运行

## 2026-10-23 最新状态与实际查词链路

已完成全量真实embedding：46,073条，text-embedding-v4／1024维／search-v1。按用户授权删除6个无法确认的极端词头及flying未确认ADJ候选，归档到私有extreme_record_archives；现有正式词头12,188个。有效义项与向量均未减少。服务器尚未部署，默认SEARCH_SEMANTIC_ENABLED=false。

- 启动时从数据库加载accepted词头及有效词形，建立内存匹配和前缀索引；数据修改后需重新加载／重启。
- GET /lookup：输入校验及IP限流 → Unicode NFC／去首尾空格／大小写归一 → 词形和词头精确匹配 → 重音及连字符变体匹配 → 无候选时使用PostgreSQL pg_trgm模糊匹配。按词头去重，返回best_match或did_you_mean。普通查词不调用embedding、不在线调用Frog或翻译模型。
- GET /suggest：内存前缀候选 → 不足时数据库模糊补足 → 按词头去重。
- POST /semantic-search：显式启用且线上预算可用后，输入描述 → Qwen3.7-Flash直接改写 → v4实时生成查询向量 → 本地pgvector比较现有义项向量 → 相似度加少量词频、等级权重 → 按词头保留最佳义项 → 返回词头、匹配义项的荷英中释义；可附加关联词和entry_url。不增加独立意图识别模型；改写失败时原文回退，Flash Key单独配置。默认取50个义项候选生成10个结果，最多250个候选。当前没有查询向量／结果缓存。线上改写和查询embedding使用共享持久化账本，累计及每日金额默认0，阻止未获预算的调用；与此前离线5元账本分开。详见[查询改写配置](query-rewrite.md)。
- 普通匹配失败不会自动转付费语义查询，语义模式目前是独立接口。未启用时返回503。
- /lookup、/suggest、语义结果及关联词返回entry_url；GET /entries/{lemma_id}读取词性、三语义项、有效词形、语料例句和表达，并按类别分页。义项例句提供预览，GET /senses/{sense_id}/examples读取完整分页及现有译文。两个新端点共享IP额度；词条/义项可见性与来源追溯已检查。Woordhuis 前端已完成本机对接，使用 `scripts/run_local_preview.py` 在同源地址提供页面和真实 API；启动方式见[前端说明](../frontend/README.md)。详见[词条详情API](entry-details-api.md)。
- 共享IP限额仍为总60次/分钟、语义10次/分钟、突发10次/10秒；超限429与Retry-After。内存限流要求当前单进程部署；可信代理必须显式配置。

本次实测并修复了模糊纠错中同一词头因多个词形／语料统计而重复返回的问题：SQL先按lemma_id选最佳匹配，再排序限条。清理后接口冒烟检查通过；本次语义检查复用已付费的查询向量，未新增API费用，这只是验证工具缓存，生产服务尚无查询缓存。

清理结果与实际检查见outputs/extreme_record_cleanup_20261023；全量向量结果见outputs/embedding_full_20261023。以下保留历史部署准备方案，当前状态以上述更新为准。

2026-10-23 已完成Flash权限配置和1元上限内的真实改写验证：14条成对输入、69个API场景；耗时中位数约693→1,440ms，小样本未证明排序提升，1例下降、1次真实超时成功回退。费用预留上界0.0033055元；生产默认预算仍为0、语义仍关闭。前端交付包包含OpenAPI、类型、fetch客户端、实际响应及本地回放服务，生成目录为outputs/frontend_api_handoff_20261023，入口API_SPEC.md。

## 2026-10-13 历史状态与采购建议

部署前修复和本地完整词库验证已完成；尚无远程服务器和百炼 Key，因此**未远程部署、未生成真实 embedding**。先运行普通查词，再验证 500 条 embedding，最后决定是否全量构建。

建议单机采购 **4 vCPU / 8 GB RAM / 80 GB SSD，Ubuntu 24.04 LTS x86_64**，API 与 PostgreSQL 共用此机，不需要 GPU。这是低流量 MVP 的保守起步配置，不是经过生产压测的并发承诺。2 核 / 4 GB 可用于测试，但不作为本项目生产采购建议。公网带宽从 5 Mbps 起步，支持扩容；数据库端口只监听本机。原始 CC100 大语料不必上传，仅迁移应用词库和代码。选择可访问所选百炼地域端点、接近主要用户的机房；Key 与 API 端点必须同地域。

本机实测：原数据库约 477 MB，独立 PostgreSQL 恢复后的业务库约 333 MB；12,194 个词条、174,861 个词形、46,674 个义项。API 常驻内存约 160 MiB，启动约 2.34 秒。这是 macOS 本地低负载测量，不能推算生产 QPS。46,674 条 1024 维 float32 向量的裸数据约 182 MiB，另需表、HNSW、WAL 和备份空间。80 GB 预留系统、日志、备份和增长空间。

## 架构与限制

公网 HTTPS → 本机 Nginx → `127.0.0.1:8080` 单进程 API → `127.0.0.1:5433` PostgreSQL 17 / pgvector。不部署公开的 Supabase REST 接口，避免绕过 API 查询限流。若今后加 CDN，必须按 CDN 的真实出口网段配置可信代理，不能信任客户端自行提供的转发头。

- 每 IP 查询总额度：滑动 60 秒内 60 次；查询包括 lookup、suggest、semantic-search、entries 详情和 senses 例句。
- 突发限制：滑动 10 秒内最多 10 次；语义查询另限 60 秒内 10 次。
- 超限返回 429 和 Retry-After；Nginx 边缘限流独立返回 429。
- 应用只信任本机 Nginx；Nginx 覆盖 X-Forwarded-For，不追加客户端值。API 和数据库均不对外开放。
- 单进程内存限流，重启后重置。扩大到多进程/多实例前需换成 Redis 等共享限流存储。共享校园网出口也共享额度，后续按实际使用调整。
- IP 限流能降低批量抓取速度，不能阻止分布式 IP 抓取。语义查询若公开推广，还需按实际费用设置账号配额或总预算。
- 请求体上限 8 KiB，普通查询 128 字符、语义查询 512 字符；没有列表导出接口。查询日志默认关闭。

## 首次部署：先普通查词

以下操作只针对**新建的独立部署库**；不要把恢复命令指向现有业务库。部署材料已本地验证，远程 Linux/systemd、TLS、网络连通性仍待服务器到位验收。

1. 安装 Docker Compose、Python 3.12 venv、Nginx；创建 `search` 系统用户。将发布包解压到 `/srv/dutch-corpus`，业务备份放到受限的备份目录。不要上传原始语料或整个 outputs。
2. 在 `/srv/dutch-corpus/deploy/.env` 中填写随机强密码 `POSTGRES_PASSWORD=...`，权限 600。不要把密码放进命令参数或 Git。
3. 在项目根目录启动数据库：

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d db
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
```

容器首次初始化会安装 vector、pg_trgm 等扩展和无登录权限的兼容角色。确认健康后恢复 public schema（不要把 Supabase 内部 extensions 辅助函数一起迁移）：

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml exec -T db \
  pg_restore -U postgres -d dutch_lexicon --schema=public --no-owner --no-acl --exit-on-error \
  < /受限备份目录/lexicon-before-deploy.dump
docker compose --env-file deploy/.env -f deploy/compose.yaml exec -T db \
  psql -U postgres -d dutch_lexicon -v ON_ERROR_STOP=1 < deploy/search-db-permissions.sql
```

4. 交互进入数据库，分别用 `\password search_service_user` 和 `\password search_indexer` 设置独立密码。API 账号只能读词库、写查询日志；构建账号可以写向量。不要用 postgres 账号运行应用。
5. 安装锁定依赖并填写 API 配置：

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-search.lock
cp deploy/search-engine.env.example deploy/search-engine.env
chmod 600 deploy/search-engine.env
```

填写 DATABASE_URL；密码包含 URI 特殊字符时需百分号编码。保持 `SEARCH_SEMANTIC_ENABLED=false`，Key 可留空。环境文件不会被 Python 自动读取，systemd 会读取它；手动运行时使用 shell 加载：

```bash
set -a
. deploy/search-engine.env
set +a
.venv/bin/python scripts/run_search_service.py
```

6. 将 `deploy/search-engine.service` 安装到 `/etc/systemd/system/`，确认 `/srv/dutch-corpus` 对 search 用户可读、环境文件只对管理员和服务账户可读。执行 `systemctl daemon-reload`、`systemctl enable --now search-engine`。
7. 安装 Nginx 配置，先 `nginx -t` 再 reload。当前模板是 HTTP 测试入口；有域名后安装证书，正式开放前启用 HTTPS 并把 HTTP 重定向到 HTTPS。安全组仅放行必要的 80/443 和受限 SSH 来源，不放行 8080/5433。没有域名时可用 SSH 隧道测试。
8. 本机验收：

```bash
curl --fail http://127.0.0.1:8080/health
.venv/bin/python scripts/run_search_benchmarks.py \
  --input tests/fixtures/lookup-smoke.json --interval 1.2 \
  --output outputs/lookup-smoke.json
```

远程还需从公网测试查词、429、伪造转发头、端口隔离、服务重启与开机启动。上面的 5 个用例只是功能冒烟测试，不代表完整准确率或负载容量。下一次负载测试应在隔离环境对多个来源模拟正常流量，保留真实限流配置。

## 500 条 embedding 验证

沿用百炼 `text-embedding-v4`，1024 维，每批最多 10 条。使用单独的受限环境文件，DATABASE_URL 指向 `search_indexer`，模型和 index version 与 API 一致；Key 只在此环境和启用语义后的 API 环境中设置。

```bash
# 先加载 indexer 环境，默认只预览，不调用 API、不写向量。
.venv/bin/python scripts/rebuild_search_index.py --limit 500 \
  --output outputs/embedding-pilot/report.json
# Key 就绪后，明确执行付费调用。
.venv/bin/python scripts/rebuild_search_index.py --limit 500 --execute \
  --output outputs/embedding-pilot/report.json
```

脚本保存带文本和 SHA256 的样本清单，覆盖等级/词性；同文本哈希自动跳过，成功批次立即落库，中断后重跑只处理未完成/已变更项。对 429、暂时性服务器错误和网络错误做有限退避重试，401 等凭据错误立即失败。会验证响应数量、索引、维度和有限非零向量。同一数据库通过 advisory lock 防止多个构建进程重叠。

构建成功后配置 API Key 并设 `SEARCH_SEMANTIC_ENABLED=true`，重启服务。启动时会检查该版本有向量且模型一致。运行：

```bash
.venv/bin/python scripts/run_search_benchmarks.py \
  --input tests/fixtures/semantic-pilot-queries.json --interval 6.1 \
  --output outputs/embedding-pilot/metrics.json
```

12 个中/英/荷查询标签由助手编写，用于链路冒烟，尚未独立人工复核。当前指标以词条 ID 计算；义项准确率需另行人工检查。检查真实向量数量/维度、重复运行是否零新增、查询命中/失败与延迟、百炼实际用量；确认样本表现后才考虑 `--all --execute`。

**样本质量限制：**已有数据包含疑似误分词、错配词性及不充分的中文翻译；例如 sample 中有 `---` 占位词条和 `een` 的疑似误配动词义项。结构补全不等于语义正确。试验保留这些来源信息供检查，不能把 500 条试验结果当成正式全库质量验收，也不能以假向量代替真实评估。

当前表只保留同一 sense/model/dimension 的一个版本。脚本拒绝隐式覆盖其他 index version 或混入其他模型；跨版本更新需安排备份和停用语义接口的离线重建，尚不支持蓝绿索引切换。

## 备份、回滚与维护

- 上线前备份；每日 `pg_dump -Fc --schema=public --no-owner --no-acl`，保存到非公开目录，定期复制到另一台设备/对象存储。按数据更新频率设置保留期并做恢复演练；目前只做了本机恢复验证，未建立远程定时备份。
- 更新应用先保存上一份发布包和环境文件。失败时切回旧包重启；本次修复没有修改业务表结构。向量试验可关闭 semantic 开关回到普通查词。
- 若开启查询日志，需设置保留期限（建议初期 7 天）并定期清理；Nginx 模板关闭访问日志。开启日志前不要忽略磁盘增长。
- 检查 systemd 状态、磁盘、数据库连接、429 比例和 API 错误。真实告警、HTTPS 和备份计划待远程部署时配置。

参考：[Uvicorn 可信代理设置](https://uvicorn.dev/settings/)、[pgvector 官方说明](https://github.com/pgvector/pgvector)、[百炼同步向量 API](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api)。

### 2026-10-23 词形与多词表达修复

发布新代码前先应用 `20261023040000_researched_source_gaps.sql`。查词加载与模糊查词会过滤 `forms.is_active=false` 的错误词形关联；停用只隔离关联，原始词形和语料统计仍保留。`lexical_expressions` 区分真正的多词表达、语法构式、义项说明和例句，不增加分级词头。该表现已通过词条详情API返回，保留entry_kind；发布详情接口时还需应用 `20261023060000_entry_detail_indexes.sql` 并重跑权限脚本。本轮不启动或重建 embedding。
