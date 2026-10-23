# Woordhuis · 荷兰语词典前端

> **Elk woord heeft meer dan één kamer.** 每个词，都有不止一个房间。

Woordhuis 是为「荷兰语词典」项目做的 Web 前端与交互设计。它消费 `dutch-lexicon-frontend-api-20261023.zip` 里的公开接口合同，覆盖三条链路——**查词**、**按意思找词**、**读完整词条**——并把接口文档里那些容易被界面藏起来的东西（来源、审核状态、置信度、限流、回退）摆到台面上。

包内 `site/` 是零依赖静态站点：双击 `site/index.html` 就能打开，不需要构建、不需要网络。

---

## 1. 快速开始

### 离线演示（默认）

```bash
cd site
python3 -m http.server 8801
# 打开 http://127.0.0.1:8801/
```

页面默认运行在**离线回放**模式：读取本包 2026-10-23 录制的 69 个真实响应。每个词条、每条例句、每张报错页都来自那次真实请求，没有为效果编造数据。

> 直接双击 `index.html`（`file://`）也能用，因为数据以 `data/fixtures.js` 内联，不靠 `fetch` 本地文件。

### 接真实接口

真实后端尚未公网部署。任一方式：

```bash
# A. 用查询参数指定 API base（会记到 localStorage）
http://127.0.0.1:8801/?api=http://127.0.0.1:8080

# B. 用包里的回放服务（需 Python 3.10+，无依赖）
python3 api-contract/mock_server.py --port 8799
http://127.0.0.1:8801/?api=http://127.0.0.1:8799
```

前端假定 **API 与页面同源**、由代理转发——真实接口目前没有配置跨域 CORS；`mock_server.py` 的 CORS 只是回放便利。

### 状态预览（给评审看）

右下角「状态预览」列出全部 69 个录制场景（正常 / 空态 / 错误 / 回退 / 分页），点一条即可强制回放该响应：429 倒计时、503 语义关闭、422 参数校验、413 请求体过大、五种改写回退……都在里面。`?inspector=0` 可隐藏。

---

## 2. 目录

```
woordhuis/
├── README.md                  ← 本文件
├── site/                      ← 交付前端（零依赖、零构建）
│   ├── index.html
│   ├── css/                   tokens · base · components · views · print
│   ├── js/
│   │   ├── api.js             接口客户端 + 离线回放适配器 + 错误归一
│   │   ├── ui.js              页头页脚、搜索 combobox、词砖、状态页、检视器
│   │   ├── views/             home · results · entry · saved · about
│   │   └── util.js            原生 DOM 构造、图标、格式化、剪贴板
│   ├── data/fixtures.js       69 个录制响应（生成自 mock/manifest.json）
│   └── assets/fonts/          4 个 OFL 字族，本地 woff2
├── api-contract/              ← 收到的接口包原样保留（合同 + 回放服务 + 录制）
├── docs/
│   ├── DESIGN.md              设计说明：概念、代尔夫特蓝、网格、字体、文化元素
│   ├── INTERACTION.md         交互规格：每个状态、键盘、限流、错误映射
│   ├── DATA.md                数据与诚信：哪些是接口、哪些是编辑性内容
│   ├── QA.md                  验收记录：跑过的路由、交互测试与结论
│   └── shots/                 截图（首页 / 联想 / 纠错 / 语义 / 词条 / 指南 / 深色 / 移动端 / 数据页）
└── serve.sh                   一条命令起本地服务
```

---

## 3. 页面与路由

| 路由 | 页面 | 说明 |
| --- | --- | --- |
| `#/` | 首页 | 搜索（查词 / 按意思）、10 个真实词砖、三条语言规则、口径 note 条 |
| `#/zoeken?q=` | 查词结果 | 命中则直接替换路由进词条；未命中展示纠错候选；空态单列 |
| `#/betekenis?q=` | 按意思找词 | 一次显式提交 → 主结果 + 独立关联词区 + 改写披露 |
| `#/woord/:id` | 词条 | 词头、词性导航、义项分页、语料、词形、表达、来源、侧栏 |
| `#/woordenschat` | 我的词库 | 只存 localStorage |
| `#/over` | 数据与方法 | 长文说明：数据、边界、设计理由、许可 |

路由用 hash，所以静态托管、`file://`、子目录都能跑。

---

## 4. 交互要点

- **两种查询不混**：联想只属于查词；语义检索只在显式提交时发一次，不绑按键。
- **命中就直接进词条**，用 `history.replaceState` 替换结果页，返回键回到搜索框而不是闪屏。
- **四组分页互不覆盖**：义项 / 词形 / 语料 / 表达各自 `offset`，加载某种下一页时丢弃同响应里其它组的第一页。
- **语义命中义项定位**：结果带到词条后，若目标义项不在第一页，按 `next_offset` 继续读到它（最多 3 页），高亮并滚动到位。
- **429 倒计时**：读 `Retry-After`，禁用提交，已加载内容保持可读。
- **改写回退照实说**：`timeout / provider_error / constraint_fallback …` 都显示「已按原描述检索」。
- **分数不叫准确率**：`score` 是加权排序分（可 >1），`confidence` 是启发式，明确标注。
- **键盘**：`⌘K` / `/` 聚焦搜索，`↑↓` 选候选，`↵` 打开，`Esc` 关闭。
- **动效**：路由入场、列表错峰、联想落入、主题径向切换、悬停与按压反馈；全部 ≤ 420ms，`prefers-reduced-motion` 下关闭。
- **无障碍**：ARIA combobox、跳转链接、焦点管理、4.5:1 对比度、`prefers-reduced-motion`。

完整规格见 [`docs/INTERACTION.md`](docs/INTERACTION.md)。

---

## 5. 关于离线回放的一个诚实说明

`site/data/fixtures.js` 把 `mock/manifest.json` 登记的全部响应内联。匹配逻辑照抄 `mock_server.py`：方法 + 路径 + 参数（含默认值）+ 请求体完全一致才回放。

**一处刻意的扩展**：当某个分页请求没有精确录制时，适配器会在**同一路径、同一 offset 区间**的已录制页里切片，返回被覆盖的那一段，并按录制里的 `total` 重算 `has_more` / `next_offset`。它只返回录制里真实存在、顺序未变的条目，不会补齐或编造。这让 `afzetten`（录制页大小 7、共 33 义项）能连续读两页；第三页没有录制，界面会显示「这次请求没有录制」而不是假装有数据。真实接口不受影响。

---

## 6. 兼容与体积

- 现代浏览器（Chrome / Safari / Edge 最近两年）。使用 `color-mix()`、`<dialog>`、`hashchange`。
- 首屏体积：HTML+CSS+JS ≈ 90 KB，字体 ≈ 726 KB（4 族，本地、`font-display: swap`），录制数据 ≈ 630 KB。
- 无构建、无框架、无运行时依赖；`site/js` 为可直接读的 ES2019。

---

## 7. 数据与许可

词库数据来自 Open Dutch WordNet 1.3（CC BY-SA 4.0）、DBnary / 荷兰语维基词典（CC BY-SA 3.0）、SUBTLEX-NL 与 CC100 Dutch（来源限定），以及项目自有的分级、译文与 AIGC 补全。**每条释义在界面上都带着它的来源、审核状态与置信度**；不同意把「显示出来的」当成「确定的」。

字体 Fraunces、Source Serif 4、Inter、IBM Plex Mono 均为 SIL OFL 1.1。所有图形（运河屋山墙、瓷砖角标、风车、logo）为本项目手绘 SVG。

详见 [`docs/DATA.md`](docs/DATA.md)。
