# 荷兰语词典 · 前端接口与真实响应包

先读 `API_SPEC.md` 设计页面；需要机器可读合同或代码补全时使用 `openapi.yaml` / `openapi.json` 和 `types.ts`。

## 文件

- `API_SPEC.md`：页面请求流程、全部接口参数、字段含义、分页、限流与错误状态。
- `openapi.yaml`、`openapi.json`：OpenAPI 3.1 合同，可导入接口设计工具。
- `types.ts`、`client.ts`：响应/请求类型与无框架依赖的 fetch 客户端示例；`client.js` 是已编译的 ES Module 版本。
- `mock/manifest.json`：已录制场景索引；同目录 `*.response.json` 为本轮实际接口响应。
- `mock_server.py`：仅监听本机的离线回放服务，不连接模型或数据库。
- `reports/真实查询验证报告.md`：本轮真实改写效果、延迟、费用及故障回退结果。
- `reports/contract-validation.json`、`reports/replay-validation.json`：响应合同和回放检查回执。
- `MANIFEST.sha256`：交付文件完整性清单。

包内不含 API Key、密钥文件、数据库地址、原始向量或完整词库。真实后端尚未公网部署。

## 启动本地 Mock

只需 Python 3.10 或以上，不需要安装依赖：

```bash
python3 mock_server.py --port 8799
```

另开终端：

```bash
curl 'http://127.0.0.1:8799/lookup?q=huizen'
curl 'http://127.0.0.1:8799/entries/138'
curl 'http://127.0.0.1:8799/__mock__/scenarios'
curl -H 'X-Mock-Scenario: error-ip-429' 'http://127.0.0.1:8799/lookup?q=huis'
```

按含义找词使用真实录制的查询；可从场景索引复制 request.json：

```bash
curl 'http://127.0.0.1:8799/semantic-search' \
  -H 'Content-Type: application/json' \
  -d '{"query":"可以通过网址访问的一组网页","limit":10,"include_related":true}'
```

回放服务只覆盖索引列出的请求；任意新输入不会执行检索，而会返回 mock 专用 501。错误、回退等状态可通过 X-Mock-Scenario 选择；它仅用于回放。localhost CORS 是回放便利功能，不是当前生产 API 的跨域配置。

## 接入 TypeScript 示例

```ts
import { LexiconClient } from './client';

const api = new LexiconClient('http://127.0.0.1:8799');
const match = await api.lookup('huizen');
if (match.best_match) {
  const entry = await api.entry(match.best_match.lemma_id);
  // entry.senses.items、entry.forms.items、entry.corpus_examples 等可用于页面布局。
}

// 单独创建一个错误状态预览客户端；该头只适用于 Mock。
const rateLimited = new LexiconClient('http://127.0.0.1:8799', 'error-ip-429');
```

普通查词和语义反查采用不同提交入口。详情加载、联想与语义查询都受真实后端共享 IP 额度限制；Mock 回放并不消耗模型额度。前端不要存储或调用百炼 Key。
