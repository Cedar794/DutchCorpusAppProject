# Woordhuis · API 查询测试页

当前前端用于辅助 API 和词库测试，只保留查询表单与响应展示。页面默认请求同源后端，原生 HTML/CSS/JavaScript，无构建步骤。

## 查询行为

- 下拉选择普通查词、语义检索、联想、词条详情或义项例句五个接口；参数名称和默认值与后端保持一致。
- 每次点击查询仅请求所选接口。`/lookup` 命中后仍展示 lookup 响应；点击 `entry_url` 才请求详情。
- 输入原样发送，不做改写、自动翻译、去重、分数组合或百分比换算。语义查询的改写由原后端负责，页面完整保留 `query_rewrite`。
- 响应按字段排版，配中文标签；数组可展开，原字段名、顺序、空值、布尔值、审核状态、分页信息和分数均保留。未知字段照常展示。
- 可展开和复制原始响应体，查看请求体、HTTP 状态、耗时与浏览器可见的响应头。HTTP 错误也完整渲染其响应体。
- 分页按接口返回的 `next_offset` 显式发起请求，展示该次完整响应，不在前端合并成另一个数据集。
- 不自动联想、不自动跳详情、不预取、不自动重试；刷新、切换接口或打开带查询参数的地址只填表，不自动发起付费查询。
- HTTP 429 时按 `Retry-After` 禁用提交并倒计时；服务端原有单 IP 限流不变。

## 连接真实后端

需先启动或连接已有词库的 PostgreSQL / Supabase（默认 `127.0.0.1:54322`）及已有 `.venv`：

```bash
# 普通接口，不调用模型
bash frontend/serve.sh --port 8801

# 本机已有密钥和原累计 1 元测试账本时，显式启用语义模型
bash frontend/serve.sh --port 8801 --semantic
```

打开 <http://127.0.0.1:8801/>。默认绑定 127.0.0.1、单进程，静态文件仅公开 `site/`。Ctrl+C 停止；前端修改后刷新，Python 修改后重启。

模型密钥仅由服务端读取 `local/secrets/embedding-pilot.env` 和 `local/secrets/query-rewrite-test.env`。预算继续复用 `local/budgets/query-rewrite-test-20261023.sqlite3`，累计和每日上限各 1 元；缺失原账本拒绝开启语义模式。普通模式云预算为 0。

限流仍是每 IP 60 次/分钟、10 秒内最多 10 次，语义额外 10 次/分钟。静态文件不计查询额度。

## 仅用已录制响应检查页面

不启动数据库或模型，在两个终端分别运行：

```bash
.venv/bin/python frontend/api-contract/mock_server.py --port 8799
.venv/bin/python -m http.server 8801 --bind 127.0.0.1 --directory frontend/site
```

打开 <http://127.0.0.1:8801/?api=http://127.0.0.1:8799>。这里只能查询 `api-contract/mock/manifest.json` 中录制的场景；未录制请求返回 mock 专用 501，不代表真实后端故障。该回放服务用于展示验证，不代替真实后端限流。

旧 hash 地址（如 `#/betekenis`、`#/zoeken?q=huizen`、`#/woord/138`）仍可用于填写相应查询表单。复制新地址可保留接口参数；页面没有账号、收藏、最近查询或本地结果缓存。原产品版的源文件和设计交付文档保留在仓库中，当前入口只加载 `console.css` 和 `test-console.js`。

## 验证

```bash
node --test tests/test_frontend_console.cjs
.venv/bin/python -m unittest tests.test_local_preview tests.test_search_runtime -q
```
