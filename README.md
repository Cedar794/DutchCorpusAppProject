# DutchCorpusAppProject · Woordhuis

荷兰语词典与语料处理项目。包含 CC100 / SUBTLEX 风格词频处理、词库补全与审核工具、PostgreSQL / pgvector 检索服务，以及 Woordhuis 网页前端。

## 当前进度

2026-10-23 的本地数据快照：12,188 个正式词头、46,073 条有效义项，中英文译义均已覆盖；已有 46,073 条真实 `text-embedding-v4` 向量（1024 维）。内容补全和模型交叉复核已完成相关批次，正式人工审校仍待推进，页面保留逐条来源和审核状态。

前端已接入真实后端，普通查词、联想、完整词条、分页和语义查询已在本机验证。2026-10-27 起，当前入口简化为 API 查询测试页：保留查询输入、接口参数和完整响应渲染，词条链接与分页均显式请求，不再加载原产品版导航、收藏、首页样张与动效。远程服务器尚未部署。本地真实服务和数据库目前保持停止。

## 本地开发

使用 Python 3.12，前端为原生 HTML/CSS/JavaScript，无 Node 构建步骤。

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-search.lock

# 需先启动或连接已恢复词库的 PostgreSQL / Supabase 数据库
bash frontend/serve.sh --port 8801
```

打开 <http://127.0.0.1:8801/>。页面和 API 同源，默认连接本机 `127.0.0.1:54322` 的数据库，也可以通过 `DATABASE_URL` 指定现有业务数据库。普通查词不需要模型密钥。

仓库包含数据库迁移、词汇分级数据和前端录制响应；完整业务数据库、向量、原始大语料、运行账本和密钥保存在仓库外，换机器时需要单独恢复。

### 语义查询

流程为 Flash 查询改写 → v4 查询向量 → pgvector 义项检索 → 按词头聚合。改写失败时使用原输入继续检索，模型请求不自动重试。语义模式默认关闭，在线预算默认 0。

本机预览可用 `--semantic` 显式启用真实模型，复用已有的累计 1 元测试账本；缺少该账本时拒绝启用。密钥仅由服务端读取。详细配置见 [前端启动说明](frontend/README.md) 和 [查询改写说明](docs/query-rewrite.md)。

### 查询限制

单 IP 共享 60 次/分钟，10 秒内最多 10 次；语义查询另限 10 次/分钟。超限返回 HTTP 429 和 `Retry-After`。当前限流适用于单进程服务。

## 目录

- `frontend/`：Woordhuis 前端、设计交互规格、接口合同和录制 mock。
- `lexicon_search/`：匹配、语义检索、词条详情、限流和在线预算。
- `cc100_subtlex/`：语料计数与 Frog 注释处理。
- `scripts/`：数据补全、交叉复核入库、索引构建、验证及启动工具。
- `supabase/migrations/`：词库、检索、审核与数据修复相关表结构迁移。
- `deploy/`：数据库容器、Nginx、systemd 和环境配置模板。
- `tests/`：单元测试与可选数据库集成测试。

## 验证

全量测试还需要语料导出工具使用的 `openpyxl`：

```bash
.venv/bin/pip install 'openpyxl>=3.1,<4'
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_frontend_console.cjs
```

本次同步前：134 项通过，4 项数据库集成测试因数据库已停止而跳过。设置 `SEARCH_TEST_DATABASE_URL` 可在隔离的测试数据库上执行这些集成测试；此前本地接入验证中这 4 项均通过。

接口说明：[词条详情 API](docs/entry-details-api.md)。部署说明：[查词服务运行](docs/search-engine-operations.md)。代码沿用仓库的 MIT 许可；词库来源和字体各自的署名、许可说明保留在前端及相关文档中。

## 云端部署与资料恢复

参见 [阿里云部署与资料恢复](docs/cloud-migration.md)，包含备案前的 SSH 隧道访问、运行路径、预算账本和备份恢复说明。
