/* ==========================================================================
   Woordhuis · about — reference, not essay
   ========================================================================== */
(function () {
  "use strict";

  const WH = (window.WH = window.WH || {});
  const { el, icon, fmt } = WH;

  const SWATCHES = [
    ["#1D3F73", "kobalt"],
    ["#0E2748", "deep"],
    ["#F7F5EF", "paper"],
    ["#FFFEFB", "tegel"],
    ["#14171C", "ink"],
    ["#B32B20", "rood"],
    ["#D99B1E", "geel"],
    ["#C14E0C", "oranje"],
  ];

  function row(label, value) {
    return el(
      "div.kv",
      null,
      el("dt", null, label),
      el("dd", null, value)
    );
  }

  function section(label, body) {
    return el(
      "section.about-col",
      null,
      el("div.about-col__side", null, el("h2", null, label)),
      el("div.about-col__body", null, body)
    );
  }

  WH.views = WH.views || {};

  WH.views.about = function () {
    const wrap = el("div");
    const recordedAt = WH.api.recordedAt && WH.api.recordedAt();

    wrap.appendChild(
      el(
        "div.wrap",
        null,
        el(
          "header.about-hero",
          null,
          el("span.eyebrow.eyebrow--kobalt", null, "Over · 数据与方法"),
          el("h1", null, "数据与方法"),
          el(
            "p.meta-line",
            null,
            el("span", null, "合同 2026-10-23"),
            WH.api.mode === "demo" ? el("span", null, "录制 " + (recordedAt ? fmt.date(recordedAt) : "2026-10-23")) : null,
            WH.api.mode === "demo" ? el("span", null, "69 个场景") : null,
            WH.api.mode === "demo" ? el("span", null, "10 个完整词条") : el("span", null, "查询与详情实时读取数据库"),
            el("span", null, WH.api.mode === "demo" ? "离线回放" : "在线接口")
          )
        ),
        section(
          "01 · 运行",
          el(
            "div",
            null,
            el(
              "dl.kv-list",
              null,
              row("当前模式", WH.api.mode === "http" ? "真实接口：查词、详情和语义结果来自本机后端" : "离线回放：69 条已录制响应"),
              row("首页样张", "精选词条计数与 huis 样张为 2026-10-23 快照；打开词条读取当前数据"),
              row("我的词库", "收藏与最近查询只保存在当前浏览器"),
              row("语义搜索", "显式提交后调用模型；失败不自动重试")
            )
          )
        ),
        section(
          "02 · 数据来源",
          el(
            "table.data-table",
            null,
            el(
              "thead",
              null,
              el("tr", null, el("th", null, "来源"), el("th", null, "用途"), el("th", null, "许可"))
            ),
            el(
              "tbody",
              null,
              [
                ["Open Dutch WordNet 1.3", "词汇语义", "CC BY-SA 4.0"],
                ["DBnary / Wiktionary", "义项与用法", "CC BY-SA 3.0"],
                ["SUBTLEX-NL", "词形与频次", "来源限定"],
                ["CC100 Dutch", "语料与例句", "来源限定"],
                ["项目词表 / 模型补全", "分级、译文、部分例句", "内部 / 派生"],
              ].map(([name, use, license]) =>
                el("tr", null, el("td", null, name), el("td", null, use), el("td", null, license))
              )
            )
          )
        ),
        section(
          "03 · 口径",
          el(
            "dl.kv-list",
            null,
            row("score", "加权排序分，可 > 1；不显示为百分比"),
            row("confidence", "启发式分数，不是校准概率"),
            row("review_status", "已审核 / 待复核 / 未复核，逐条显示"),
            row("article · gender", "接口有值才显示，否则留空"),
            row("sense_disambiguated", "false 时语料例句独立成区，不挂义项"),
            row("query_rewrite", "回退状态显示「已按原描述搜索」"),
            row("level", "项目分级 1–4，不是 CEFR")
          )
        ),
        section(
          "04 · 限流",
          el(
            "dl.kv-list",
            null,
            row("全部公开端点", "60 次/分钟 · 10 秒最多 10 次"),
            row("语义查询", "10 次/分钟"),
            row("请求体", "8 KiB"),
            row("429", "读 Retry-After 倒计时；不自动重试语义查询")
          )
        ),
        section(
          "05 · 不做的事",
          el(
            "ul.plain-list",
            null,
            el("li", null, "不编音标：接口没有 IPA，界面一个都不造"),
            el("li", null, "不补冠词、词性、变位：缺失即留空"),
            el("li", null, "不在前端调模型翻译例句"),
            el("li", null, "不把「未录制」说成服务错误")
          )
        ),
        section(
          "06 · 设计",
          el(
            "div",
            null,
            el(
              "p",
              null,
              "代尔夫特蓝 + De Stijl 网格；运河屋山墙、瓷砖、风车均为手绘 SVG。"
            ),
            el(
              "div.swatches",
              null,
              SWATCHES.map(([hex, name]) =>
                el(
                  "div.swatch",
                  {
                    style: `background:${hex};color:${["#F7F5EF", "#FFFEFB", "#D99B1E"].includes(hex) ? "#14171C" : "#fff"}`,
                  },
                  el("span", null, name),
                  el("span", { style: "opacity:.72;margin-top:2px" }, hex)
                )
              )
            )
          )
        ),
        section(
          "07 · 许可",
          el(
            "dl.kv-list",
            null,
            row("词库", "各来源许可见上表；转载保留署名"),
            row("字体", "Fraunces · Source Serif 4 · Inter · IBM Plex Mono（OFL 1.1）"),
            row("图形", "本项目手绘 SVG")
          )
        ),
        section(
          "08 · 键盘",
          el(
            "dl.kv-list",
            null,
            row("聚焦搜索", el("span", null, el("kbd.kbd", null, "⌘K"), " / ", el("kbd.kbd", null, "/"))),
            row("选择候选", el("span", null, el("kbd.kbd", null, "↑"), el("kbd.kbd", null, "↓"), " ", el("kbd.kbd", null, "↵"))),
            row("关闭弹层", el("kbd.kbd", null, "Esc"))
          )
        )
      )
    );

    return wrap;
  };
})();
