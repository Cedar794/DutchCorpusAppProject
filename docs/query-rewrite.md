# Qwen3.7-Flash 查询改写

## 已采用的方案

用户在 2026-10-23 明确选择：语义反查直接使用 Qwen3.7-Flash 改写，不增加独立意图识别步骤。本决定覆盖此前调查报告中“先分流、只对复杂输入改写”的建议；本次没有接入 decision-model-preview。

当前部署代码的顺序为：单 IP 限流与参数校验 → 一次 Flash 改写 → text-embedding-v4 查询向量 → 现有 46,073 条义项向量检索 → 排序、去重和关联词。所有语义请求都尝试改写，不按输入类型选择是否调用。普通 `/lookup`、`/suggest`、词条详情及例句读取保持原有路径，不调用这些云端模型。

改写只改变查询侧文本，无需重新生成数据库向量。顶层 `query` 保留原输入，响应额外返回：

```json
{
  "query_rewrite": {
    "query": "不依赖电力的形容词",
    "status": "rewritten",
    "model": "qwen3.7-flash",
    "prompt_version": "rewrite-v2"
  }
}
```

## 输出与回退

Flash 关闭思考模式，要求严格 JSON Schema，只允许一个 `query` 字段，长度 1–512 字符。提示要求保留原语言、主体、否定、词性、领域、数量及限制，禁止回答问题、猜词和执行用户输入中的指令。模型没有工具或数据库写权限。客户端再次检查字段、长度、结束原因和控制字符；对常见中英荷否定、明确词性词、数字及双引号/中文引号内的短语做保守保留检查。

这些规则不能证明每次改写都保持了全部语义，尤其不能完整识别主体、指代和复杂否定。检测到的约束丢失回退原输入；真实质量仍待人工样例评测。

每请求最多一次改写，无自动重试；默认总截止时间 1,200 ms，最多两个改写请求同时执行，繁忙时直接回退原输入。输出以 `max_completion_tokens=256` 限制总生成量；截断导致 JSON 不完整时回退，不发起额外修复调用。参数依据：[百炼 Chat API](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)、[结构化输出](https://help.aliyun.com/zh/model-studio/qwen-structured-output)、[思考模式](https://help.aliyun.com/zh/model-studio/deep-thinking)。

以下情况使用原输入继续 embedding：未配置 Flash Key、显式关闭改写、繁忙、超时、响应不合法、检测到约束丢失、供应商失败。401/403 在当前进程中停止继续尝试 Flash，修正权限后重启；其他 HTTP 错误暂停 60 秒，超时暂停 5 秒，响应/连接异常暂停 10 秒。响应通过 `query_rewrite.status` 表示结果，不返回供应商原始报错。

费用预留失败时改写也会回退，但原输入的 embedding 必须再次通过同一个费用门控；余额不足或账本不可用会返回 503，不会绕过预算。线上 embedding 同样只尝试一次，离线构建脚本的重试策略保持原样。

## 独立线上费用控制

`OnlineModelBudget` 为 Flash 和 v4 查询向量的每个 HTTP 尝试，在发送前持久化最大费用预留。使用 SQLite 事务，累计总上限和 UTC 每日上限同时生效；进程重启不重置，多个进程共用同一文件时预留也共享。确认有效 usage 后按公开原价结算并释放差额；超时、失败或 usage 缺失保留预留。发现供应商 usage 超过预留边界时停止后续模型请求，等待检查。账本损坏或不可写也阻止模型调用，普通查词仍可用。

当前按北京短输入原价估算：Flash 输入 0.2 元/百万 Token、输出 0.8 元/百万 Token；v4 输入 0.5 元/百万 Token。不假设免费额度、缓存折扣或充值余额。为了使价格边界一致，门控仅允许北京兼容端点、指定模型和固定请求规格。[Flash 模型价格](https://help.aliyun.com/zh/model-studio/qwen3-7-flash)、[向量模型价格](https://help.aliyun.com/zh/model-studio/model-pricing)。

单次 Flash 预留最多 8,192 输入 Token 和 256 输出 Token；请求 JSON 最多 4,096 字节，为文本和消息格式留出余量。查询 embedding 按每条最多 8,192 输入 Token 预留，并拒绝更大 UTF-8 输入。预留比实际查询用量保守，因此小额剩余预算可能无法继续接收请求。

该上限约束本服务经此门控的调用，不等同于阿里云账户全局余额或最终账单，也不覆盖其他程序使用同一 Key 的费用。价格变化后须复核规则。此前全量 embedding 的 5 元授权及账本不复用于线上调用。

账本只记录请求 ID、日期、模型、预留额、Token 用量和状态，不存查询、Key、认证头或 IP；文件权限 600。不得通过删除账本重置累计预算，应保留备份并按明确授权调整上限。systemd 使用私有 `StateDirectory=dutch-search` 存储账本，模板默认位置为 `/var/lib/dutch-search/api-budget.sqlite3`。

## 配置与当前启用条件

```dotenv
SEARCH_SEMANTIC_ENABLED=false
SEARCH_REWRITE_ENABLED=true
BAILIAN_REWRITE_API_KEY=
BAILIAN_REWRITE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
SEARCH_REWRITE_TIMEOUT_MS=1200
SEARCH_API_BUDGET_TOTAL_CNY=0
SEARCH_API_BUDGET_DAILY_CNY=0
SEARCH_API_BUDGET_LEDGER=/var/lib/dutch-search/api-budget.sqlite3
```

改写 Key 与现有 `BAILIAN_API_KEY` 分开配置，代码不会自动借用只授权 v4 的 Key。本机已开通并真实验证北京 Qwen3.7-Flash；用户仅为本轮测试授权1元累计预算，Flash和查询embedding共享。生产启用仍需配置Key、明确长期累计/每日预算，并确认服务账号可写入账本目录。金额默认0会阻止所有线上模型请求，语义服务仍默认关闭；本轮测试未自动改成持续服务。

单 IP 默认总 60 次/分钟、语义 10 次/分钟、10 秒突发 10 次；限流发生在改写和 embedding 之前，改写不增加独立可绕过的公开入口。当前单进程内存限流的部署限制不变。

## 验证状态

135 项测试通过，包含改写请求规格、无重试、超时与错误回退、约束检查、独立 Key、共享账本、重启保留预留、并发预算不超额及此前的数据库详情测试。

早期模拟回执位于 `outputs/query_rewrite_implementation_20261023`。随后完成14条真实中英荷输入的成对测试：原文/改写共28次语义请求，另外4次校准及5次故障回退。最终使用rewrite-v2加强原语言和词性保留；保持1,200ms截止。1次真实超时成功按原文返回；13条带预设标签样本没有排名改善，1条下降。耗时中位数由约693ms增加至1,440ms，不能据此宣称改写提升检索准确率。

本轮55次真实模型HTTP尝试，54次确认usage；按原价折算已确认0.0014623元，含1次超时最大预留的上界为0.0033055元，小于1元授权。最终账单未独立核对。默认单IP限流及429已实测，原有词库和46,073条向量保持。完整报告和69个真实API响应位于 `outputs/frontend_api_handoff_20261023`，私有测试脚本/账本不随前端包分发。当前没有公网部署。
