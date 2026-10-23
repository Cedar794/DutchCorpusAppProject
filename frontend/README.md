# Woordhuis 本地开发与预览

前端已接入本项目真实 FastAPI 服务。页面和 API 使用同一地址，保留原始 HTML/CSS/SVG/字体设计，无 Node 依赖或构建步骤。

## 启动

在项目根目录执行，需本机 Supabase/PostgreSQL 已启动（默认 127.0.0.1:54322）与已有 `.venv`：

```bash
# 普通查词、联想、完整详情；不调用云模型
bash frontend/serve.sh --port 8801

# 加上真实 Flash 改写和 v4 语义检索，沿用已批准的累计 1 元测试预算
bash frontend/serve.sh --port 8801 --semantic
```

打开 <http://127.0.0.1:8801/>。在启动终端按 Ctrl+C 停止。修改前端后刷新即可；修改 Python 后重启服务。

本次预览通过 `scripts/run_local_preview.py` 启动（端口 8801）。默认只绑定 127.0.0.1、单进程、不信任转发头，不对局域网或公网开放。

## 接口与数据

- 页面默认 `http` 模式；`/lookup`、`/suggest`、`/entries/:id`、`/senses/:id/examples`、`/semantic-search` 都直接使用原后端处理函数、数据库与限流中间件。
- 全站查询共享每 IP 60 次/分钟、10 秒内 10 次；语义搜索另限 10 次/分钟。静态资源不计查询额度。
- 真实请求失败会展示后端错误；不会自动转为录制响应。语义搜索只在显式提交后调用，不自动重试。
- `--semantic` 在服务端读取 `local/secrets/embedding-pilot.env` 和 `local/secrets/query-rewrite-test.env`，密钥不会发送到浏览器。环境变量可覆盖已有密钥和 DATABASE_URL。
- 云调用复用 `local/budgets/query-rewrite-test-20261023.sqlite3`，累计和每日上限各 1 元。旧调用、超时保留的预留额度继续计入；缺失旧账本拒绝启动语义模式。普通模式默认云预算为 0。
- 首页精选词砖计数与 huis 样张保留交付包中的 2026-10-23 快照并明确标注；打开词条后显示数据库当前内容。收藏和最近查询保存在浏览器 localStorage，无账号同步。

## 离线设计评审

在当前服务上访问 <http://127.0.0.1:8801/?mode=demo> 可切到 69 条录制响应，桌面显示状态预览。只在这个明确指定的模式使用 mock；返回无参数首页恢复真实接口。直接打开 site/index.html 也为离线模式。

原始交付说明保存在 [README-delivery.md](README-delivery.md)，设计和交互规格分别见 [docs/DESIGN.md](docs/DESIGN.md)、[docs/INTERACTION.md](docs/INTERACTION.md)。原始接口合同位于 api-contract/。只有 site/ 被 HTTP 服务公开，文档、仓库与 local/secrets/ 都不可通过预览服务访问。

## 验证

```bash
.venv/bin/python -m unittest tests.test_local_preview tests.test_search_runtime tests.test_entry_details -v
```

本地验证记录见项目 outputs/frontend_preview_20261023/。
