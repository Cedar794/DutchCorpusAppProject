/* ==========================================================================
   Woordhuis · results
   Two different submission paths, deliberately not merged:
     · lookup   — GET /lookup, cheap, debounced suggestions lead here
     · semantic — POST /semantic-search, one explicit submit, costs a model call
   ========================================================================== */
(function () {
  "use strict";

  const WH = (window.WH = window.WH || {});
  const { el, icon, fmt } = WH;
  const ui = WH.ui;

  /* results already paid for in this tab: never re-POST on back/forward */
  const semanticCache = new Map();
  WH.cache = WH.cache || {};
  WH.cache.semanticByLemma = WH.cache.semanticByLemma || new Map();
  WH.cache.clearSemantic = () => semanticCache.clear();

  function resultsHead({ mode, query, count, hint }) {
    return el(
      "div.results-head",
      null,
      el(
        "div",
        { style: "display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between" },
        el(
          "div",
          { style: "display:flex;gap:10px;align-items:center" },
          el("span.mode-note", null, mode),
          hint ? el("span.panel__count", null, hint) : null
        ),
        el("div.results-count", null, count ? el("span", null, count) : null)
      ),
      el("h1.query-quote", { style: "margin-top:14px" }, "「" + query + "」")
    );
  }

  function candidateRow(candidate, query) {
    return el(
      "a.dym__row",
      {
        href: WH.router.build("entry", { id: candidate.lemma_id }, {
          q: query,
          form: candidate.form || "",
          mt: candidate.match_type,
        }),
      },
      el(
        "span",
        null,
        el(
          "span.dym__word",
          null,
          WH.withDigraph(candidate.lemma),
          candidate.form && candidate.form !== candidate.lemma
            ? el("span.mono", { style: "font-size:11px;color:var(--kobalt)" }, "← " + candidate.form)
            : null
        ),
        el(
          "span.dym__meta",
          { style: "display:block;margin-top:4px" },
          [
            WH.labels.match[candidate.match_type] || candidate.match_type,
            candidate.level ? "L" + candidate.level : null,
            "score " + fmt.score(candidate.score),
            "confidence " + fmt.conf(candidate.confidence),
          ]
            .filter(Boolean)
            .join("  ·  ")
        )
      ),
      el(
        "span",
        { style: "display:flex;align-items:center;gap:8px" },
        ui.levelTicket(candidate.level),
        icon("arrowRight", { size: 16 })
      )
    );
  }

  /* ----------------------------------------------------------------- lookup */

  WH.views = WH.views || {};

  WH.views.lookup = function (route, mount) {
    const query = (route.query.q || "").trim();
    const wrap = el("div.wrap.result-page");

    if (!query) {
      wrap.appendChild(
        ui.state({
          code: "LEEG · 空",
          title: "还没有输入要查的词",
          text: "输入词头或任意词形，例如 huizen。",
          actions: [
            el("a.btn.btn--primary", { href: WH.router.build("home") }, "回到首页搜索"),
          ],
          iconName: "search",
        })
      );
      return wrap;
    }

    wrap.appendChild(ui.skeletonResults());
    mount(wrap);

    const controller = new AbortController();
    let cancelled = false;
    WH.api
      .lookup(query, controller.signal)
      .then((res) => {
        if (cancelled) return;
        if (res.best_match) {
          // an explicit hit: go straight to the entry, replacing this route so
          // that "back" returns to the search box rather than a spinner.
          WH.router.go(
            "entry",
            { id: res.best_match.lemma_id },
            { q: query, form: res.best_match.form || "", mt: res.best_match.match_type },
            { replace: true }
          );
          return;
        }
        renderResult(res);
      })
      .catch((err) => {
        if (cancelled || err.kind === "aborted") return;
        wrap.replaceChildren();
        wrap.appendChild(ui.errorPanel(err, { retry: () => WH.router.go("lookup", {}, { q: query }) }));
      });

    function renderResult(res) {
      wrap.replaceChildren();
      const suggestions = res.did_you_mean || [];

      if (suggestions.length) {
        wrap.appendChild(
          resultsHead({
            mode: "LOOKUP · 词形查词",
            query,
            count: `${suggestions.length} 个候选`,
            hint: "best_match = null",
          })
        );
        wrap.appendChild(
          el(
            "div.notice.notice--warn",
            { style: "margin-bottom:22px" },
            icon("alert", { size: 15 }),
            el("div", null, el("b", null, "未命中。"), "下列为纠错与近似候选。")
          )
        );
        wrap.appendChild(el("div.dym", null, suggestions.map((c) => candidateRow(c, query))));
        wrap.appendChild(
          el(
            "div",
            { style: "display:flex;gap:10px;flex-wrap:wrap;margin-top:28px" },
            el(
              "button.btn.btn--ghost",
              {
                attrs: { type: "button" },
                onClick: () => WH.router.go("semantic", {}, { q: query }),
              },
              "改用「按意思找词」",
              icon("arrowRight", { size: 14 })
            ),
            el(
              "a.btn.btn--quiet",
              { href: WH.router.build("home") },
              "回到首页"
            )
          )
        );
        return;
      }

      wrap.appendChild(
        resultsHead({
          mode: "LOOKUP · 词形查词",
          query,
          count: "0 个候选",
          sub: "接口返回了空结果：best_match 与 did_you_mean 都为空。这是正常空态，不是错误。",
        })
      );
      wrap.appendChild(
        ui.state({
          code: "LEEG · 空态",
          title: "没有这个词",
          text: "换个拼写，或者按意思找。",
          actions: [
            el(
              "button.btn.btn--primary",
              {
                attrs: { type: "button" },
                onClick: () => WH.router.go("semantic", {}, { q: query }),
              },
              "按意思找词"
            ),
            el("a.btn.btn--ghost", { href: WH.router.build("home") }, "换个词"),
          ],
          iconName: "windmill",
        })
      );
    }

    return function cleanup() {
      cancelled = true;
      controller.abort();
    };
  };

  /* --------------------------------------------------------------- semantic */

  function scoreBar(value, max) {
    const ratio = Math.max(0.02, Math.min(1, (value || 0) / (max || 1)));
    return el(
      "div.score__bar",
      null,
      el("i.score__fill", { style: "width:" + (ratio * 100).toFixed(1) + "%" })
    );
  }

  function reasonRow(result) {
    const reasons = result.matched_reason || {};
    const keys = Object.keys(reasons);
    if (!keys.length) return null;
    const labels = {
      semantic_score: "向量相似度",
      frequency_boost: "频次加权",
      level_boost: "分级加权",
    };
    return el(
      "details",
      { style: "margin-top:10px" },
      el(
        "summary",
        {
          style:
            "cursor:pointer;font-family:var(--font-mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3)",
        },
        "排序构成"
      ),
      el(
        "div",
        { style: "display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:8px;font-size:11px;color:var(--ink-3)" },
        keys.map((k) =>
          el(
            "span",
            null,
            el("span", { style: "font-family:var(--font-mono)" }, (labels[k] || k) + " "),
            fmt.score(reasons[k])
          )
        ),
        el(
          "span",
          { style: "width:100%;color:var(--ink-3)" },
          "最终 score 是加权排序分，可能大于 1，不是准确率百分比。"
        )
      )
    );
  }

  function semanticRow(result, index, query) {
    WH.cache.semanticByLemma.set(Number(result.lemma_id), result);
    const sense = result.matched_sense || {};
    const gloss = sense.translation_zh || sense.translation_en || "";
    const secondary = sense.translation_zh ? sense.translation_en : "";
    const href = WH.router.build("entry", { id: result.lemma_id }, {
      q: query,
      sense: String(sense.sense_id || ""),
      via: "semantic",
    });

    // the row is a grid, not one big <a>: the score breakdown is a <details>
    // and must stay independently operable.
    return el(
      "div.result",
      null,
      el("span.result__rank", null, String(index + 1).padStart(2, "0")),
      el(
        "div",
        { style: "min-width:0" },
        el(
          "a.result__link",
          { href, attrs: { "aria-label": result.lemma + " — 打开词条" } },
          el(
            "span.result__lemma",
            null,
            WH.withDigraph(result.lemma),
            ui.levelTicket(result.level)
          ),
          el(
            "span.result__sense",
            null,
            gloss ? el("span.zh", null, gloss) : null,
            secondary ? el("span.nl", null, secondary) : null,
            sense.definition_nl ? el("span.nl", null, sense.definition_nl) : null
          )
        ),
        reasonRow(result)
      ),
      el(
        "span.score",
        null,
        scoreBar(result.score, 0.7),
        el("span.score__val", null, "score " + fmt.score(result.score)),
        el(
          "a.result__open",
          { href, attrs: { "aria-hidden": "true", tabindex: "-1" } },
          "词条",
          icon("arrowRight", { size: 12 })
        )
      )
    );
  }

  function relatedBlock(related) {
    if (!related || !related.length) return null;
    return el(
      "section.related",
      null,
      el(
        "div.section-head",
        { style: "borderBottom:'none'" },
        el(
          "div",
          null,
          el("span.eyebrow", null, "关系扩展 · 非语义命中"),
          el(
            "h2",
            { style: "font-family:var(--font-display);font-size:1.35rem;margin-top:6px;font-weight:380" },
            "关联词"
          )
        ),
        el("span.panel__count", null, related.length + " 个")
      ),
      el(
        "div.related-grid",
        null,
        related.map((r) =>
          el(
            "a.related-item",
            { href: WH.router.build("entry", { id: r.lemma_id }) },
            el("span.related-item__word", null, WH.withDigraph(r.lemma)),
            el(
              "span.related-item__meta",
              null,
              (WH.labels.relation[r.relation_type] || r.relation_type) +
                (r.source === "sense_relations" ? " · 义项关系" : " · 词头关系")
            )
          )
        )
      )
    );
  }

  function rewriteBlock(payload, query) {
    const rewrite = payload.query_rewrite || {};
    const status = rewrite.status;
    const fallback = status && status !== "rewritten" && status !== "unchanged";
    const changed = status === "rewritten" && rewrite.query && rewrite.query !== query;

    const rows = [];
    if (changed) rows.push(["检索用", rewrite.query]);
    rows.push([
      "改写",
      (WH.labels.rewrite[status] || status || "—") +
        (rewrite.prompt_version ? " · " + rewrite.prompt_version : ""),
    ]);

    return el(
      "div.rewrite",
      null,
      fallback
        ? el(
            "div.notice.notice--warn",
            { style: "margin:-4px -4px 10px" },
            icon("info", { size: 15 }),
            el("div", null, el("b", null, "改写失败。"), "已按原描述检索。")
          )
        : null,
      el(
        "dl",
        { style: "display:grid;gap:6px;margin:0" },
        rows.map(([k, v]) =>
          el(
            "div.rewrite__row",
            null,
            el("dt", null, k),
            el("dd", null, v)
          )
        ),
        el(
          "div.rewrite__row",
          null,
          el("dt", null, "原输入"),
          el("dd", null, query)
        )
      )
    );
  }

  WH.views.semantic = function (route, mount) {
    const query = (route.query.q || "").trim();
    const wrap = el("div.wrap.result-page");

    if (!query) {
      wrap.appendChild(
        ui.state({
          code: "BETEKENIS · 按意思",
          title: "用一句话描述你要找的词",
          text: "用中文、英文或荷兰语描述你要的词。提交一次 = 一次模型调用。",
          actions: [
            el("a.btn.btn--primary", { href: WH.router.build("home") }, "去写一句描述"),
          ],
          iconName: "search",
        })
      );
      return wrap;
    }

    const cached = semanticCache.get(query);
    if (cached) {
      render(cached);
      return;
    }

    const controller = new AbortController();
    let cancelled = false;
    const started = Date.now();

    const stage = el(
      "div.stagebar",
      null,
      el("span", null, "改写描述 → 向量检索"),
      el("div.stagebar__track"),
      el("span.stagebar__elapsed", null, "0.0s")
    );
    const ticker = setInterval(() => {
      const node = stage.querySelector(".stagebar__elapsed");
      if (node) node.textContent = ((Date.now() - started) / 1000).toFixed(1) + "s";
    }, 100);

    wrap.appendChild(
      resultsHead({ mode: "BETEKENIS · 按意思找词", query, count: "检索中" })
    );
    wrap.appendChild(stage);
    wrap.appendChild(ui.skeletonResults());
    mount(wrap);

    WH.api
      .semantic({ query, limit: 10, include_related: true }, controller.signal)
      .then((payload) => {
        if (cancelled) return;
        clearInterval(ticker);
        semanticCache.set(query, payload);
        render(payload);
      })
      .catch((err) => {
        if (cancelled || err.kind === "aborted") return;
        clearInterval(ticker);
        wrap.replaceChildren();
        wrap.appendChild(
          resultsHead({ mode: "BETEKENIS · 按意思找词", query, count: "失败" })
        );
        wrap.appendChild(
          ui.errorPanel(err, {
            retry: () => WH.router.go("semantic", {}, { q: query }),
            query,
          })
        );
      });

    function render(payload) {
      wrap.replaceChildren();
      const results = payload.results || [];
      const related = payload.related_results || [];
      WH.store.addRecent(query, "semantic");

      wrap.appendChild(
        resultsHead({
          mode: "BETEKENIS · 按意思找词",
          query,
          count: `${results.length} 个结果 · ${related.length} 个关联词`,
          hint: "按排序分",
        })
      );

      const rewrite = rewriteBlock(payload, query);
      if (rewrite) wrap.appendChild(rewrite);

      if (!results.length) {
        wrap.appendChild(
          ui.state({
            code: "LEEG · 空态",
            title: "没有检索到",
            text: "换个说法，或减少限定条件。",
            actions: [
              el("a.btn.btn--primary", { href: WH.router.build("home") }, "重新描述"),
            ],
            iconName: "windmill",
          })
        );
        return;
      }

      wrap.appendChild(
        el(
          "div",
          { style: "margin-top:26px" },
          el(
            "div.panel__head",
            null,
            el(
              "div.panel__title",
              null,
              el("b", null, "主结果"),
              el("span.panel__count", null, "按排序分")
            ),
            el("span.panel__count", null, "不是准确率")
          ),
          el(
            "div.result-list",
            null,
            results.map((r, i) => semanticRow(r, i, query))
          )
        )
      );

      const relatedNode = relatedBlock(related);
      if (relatedNode) wrap.appendChild(relatedNode);

      wrap.appendChild(
        el(
          "div",
          { style: "margin-top:34px;display:flex;gap:10px;flex-wrap:wrap" },
          el(
            "button.btn.btn--ghost",
            { attrs: { type: "button" }, onClick: () => {
              semanticCache.delete(query);
              WH.router.go("semantic", {}, { q: query });
            } },
            "重新检索",
            icon("clock", { size: 14 })
          ),
          el("a.btn.btn--quiet", { href: WH.router.build("home") }, "换个说法")
        )
      );
    }

    return function cleanup() {
      cancelled = true;
      clearInterval(ticker);
      controller.abort();
    };
  };
})();
