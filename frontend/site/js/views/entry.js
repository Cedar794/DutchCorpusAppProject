/* ==========================================================================
   Woordhuis · entry
   One lemma, many rooms. Four independent pages (senses, forms, corpus,
   expressions) load without overwriting each other, per the API contract.
   ========================================================================== */
(function () {
  "use strict";

  const WH = (window.WH = window.WH || {});
  const { el, icon, fmt, highlight } = WH;
  const ui = WH.ui;

  const PAGE = { senses: 20, forms: 50, corpus: 5, expressions: 20 };
  const PARAM = {
    senses: ["sense_offset", "sense_limit", "sense_id"],
    forms: ["form_offset", "form_limit", "form_id"],
    corpus: ["example_offset", "example_limit", "lemma_example_id"],
    expressions: ["expression_offset", "expression_limit", "expression_id"],
  };
  const GROUP_KEY = {
    senses: "senses",
    forms: "forms",
    corpus: "corpus_examples",
    expressions: "expressions",
  };

  const SEPARABLE_PREFIXES = [
    "aan", "af", "bij", "door", "in", "langs", "mee", "na", "om", "onder",
    "op", "over", "rond", "samen", "tegen", "terug", "toe", "uit", "vast",
    "voor", "weg",
  ];

  function detectSeparable(lemma, forms) {
    const word = String(lemma || "").toLowerCase();
    if (word.length < 5) return null;
    for (const prefix of SEPARABLE_PREFIXES) {
      if (!word.startsWith(prefix) || word.length - prefix.length < 3) continue;
      const rest = word.slice(prefix.length);
      const evidence = [];
      for (const form of forms) {
        const f = String(form.form || "").toLowerCase();
        if (f === word || f.length <= prefix.length || !f.startsWith(prefix)) continue;
        const tail = f.slice(prefix.length);
        if (tail.startsWith("ge") && tail.length > 3) evidence.push(form.form);
        else if (rest.startsWith(tail) && tail.length >= 3) evidence.push(form.form);
      }
      if (evidence.length) {
        return { prefix, rest, evidence: [...new Set(evidence)].slice(0, 4) };
      }
    }
    return null;
  }

  function dedupePos(parts) {
    const seen = new Map();
    for (const pos of parts || []) {
      const key = pos.app_pos || pos.pos;
      const hit = seen.get(key);
      if (!hit) seen.set(key, { ...pos, sources: [pos.pos] });
      else hit.sources.push(pos.pos);
    }
    return [...seen.values()];
  }

  function sourceMap(sources) {
    const map = new Map();
    for (const s of sources || []) map.set(s.source_id, s);
    return map;
  }

  function sourceName(map, id) {
    const s = map.get(id);
    return s ? s.name : id == null ? "" : "来源 " + id;
  }

  /* --------------------------------------------------------------- header -- */

  function headBlock(entry, route, ctx) {
    const lang = WH.store.state.prefs.glossLang;
    const senses = entry.senses.items || [];
    const primary =
      senses.find((s) => s.is_primary) || senses.find((s) => s.is_core) || senses[0] || null;
    const gloss = primary
      ? WH.senseGloss(primary, lang === "nl" ? "en" : lang)
      : "";

    const appPos = [];
    const seen = new Set();
    for (const pos of entry.parts_of_speech || []) {
      const key = pos.app_pos || pos.pos;
      if (seen.has(key)) continue;
      seen.add(key);
      appPos.push(pos);
    }

    const matchBanner =
      route.query.form && route.query.form !== entry.lemma
        ? el(
            "div.match-banner",
            null,
            el("b", null, route.query.form),
            el("span", null, "→"),
            el("b", null, entry.lemma),
            route.query.mt
              ? el("span.muted", null, WH.labels.match[route.query.mt] || route.query.mt)
              : null
          )
        : null;

    const semanticBanner =
      route.query.via === "semantic"
        ? el(
            "div.match-banner",
            { style: "border-color:var(--geel);background:color-mix(in srgb, var(--geel) 12%, transparent)" },
            icon("info", { size: 13 }),
            el("span", null, "语义命中已高亮"),
          )
        : null;

    const saveBtn = el(
      "button.btn.btn--ghost.btn--sm",
      {
        attrs: { type: "button" },
        onClick: () => {
          const on = WH.store.toggleSave({
            lemma_id: entry.lemma_id,
            lemma: entry.lemma,
            gloss,
            level: entry.level,
          });
          saveBtn.replaceChildren(
            icon(on ? "bookmarkOn" : "bookmark", { size: 14 }),
            on ? "已收进词库" : "收进词库"
          );
        },
      },
      icon(WH.store.isSaved(entry.lemma_id) ? "bookmarkOn" : "bookmark", { size: 14 }),
      WH.store.isSaved(entry.lemma_id) ? "已收进词库" : "收进词库"
    );

    return el(
      "header.headword-block",
      null,
      el(
        "div",
        { style: "display:flex;justify-content:space-between;gap:20px;align-items:flex-end;flex-wrap:wrap" },
        el(
          "div",
          { style: "min-width:0" },
          el(
            "div.headword-line",
            null,
            el("h1.headword", null, WH.withDigraph(entry.display_lemma || entry.lemma)),
            gloss ? el("span.headword-gloss", null, gloss) : null
          ),
          el(
            "div.tag-row",
            { style: "margin-top:14px" },
            ui.levelTicket(entry.level),
            entry.cefr_level
              ? el("span.ticket", { attrs: { title: "CEFR 等级" } }, entry.cefr_level)
              : null,
            entry.is_academic ? el("span.ticket.ticket--academic", null, "学术词") : null,
            entry.needs_review ? el("span.ticket.ticket--geel", null, "待复核") : null,
            appPos.map((pos) =>
              el(
                "span.ticket.ticket--kobalt",
                { attrs: { title: pos.pos } },
                WH.posLabel(pos, lang)
              )
            )
          )
        ),
        el(
          "div.entry-actions",
          null,
          saveBtn,
          ui.copyButton(location.origin + location.pathname + WH.router.build("entry", { id: entry.lemma_id }), "复制链接", {
            toast: "词条链接已复制",
          }),
          el(
            "button.btn.btn--quiet.btn--sm",
            { attrs: { type: "button" }, onClick: () => ui.openGuide() },
            "语言指南"
          )
        )
      ),
      el(
        "dl.meta-strip",
        null,
        el(
          "div",
          null,
          el("dt", null, "义项"),
          el("dd", null, fmt.num(entry.senses.total))
        ),
        el(
          "div",
          null,
          el("dt", null, "词形"),
          el("dd", null, fmt.num(entry.forms.total))
        ),
        el(
          "div",
          null,
          el("dt", null, "语料例句"),
          el("dd", null, fmt.num(entry.corpus_examples.total))
        ),
        el(
          "div",
          null,
          el("dt", null, "表达 / 构式"),
          el("dd", null, fmt.num(entry.expressions.total))
        ),
        el(
          "div",
          null,
          el(
            "dt",
            { attrs: { title: "当前排序采用的语料频次，不是百分比，也不是学习人数" } },
            "语料频次"
          ),
          el("dd.num", null, fmt.num(entry.frequency))
        ),
        entry.word_family
          ? el(
              "div",
              null,
              el("dt", null, "词族"),
              el(
                "dd",
                null,
                entry.family_head_lemma_id
                  ? el(
                      "a",
                      { href: WH.router.build("entry", { id: entry.family_head_lemma_id }) },
                      entry.word_family
                    )
                  : entry.word_family
              )
            )
          : null,
        el(
          "div",
          null,
          el("dt", null, "来源"),
          el("dd", null, fmt.num(entry.sources.length) + " 个")
        )
      ),
      matchBanner,
      semanticBanner
    );
  }

  /* ---------------------------------------------------------------- senses -- */

  function senseCard(sense, entry, ctx, index) {
    const lang = WH.store.state.prefs.glossLang;
    const src = ctx.sources;
    const gloss = WH.senseGloss(sense, lang);
    const secondary = WH.senseSecondary(sense, lang);
    const isTarget = ctx.targetSenseId && Number(ctx.targetSenseId) === Number(sense.sense_id);
    const words = ctx.highlightWords;

    const tags = [];
    if (sense.is_core) tags.push(el("span.ticket.ticket--kobalt", null, "核心"));
    if (sense.is_primary && !sense.is_core) tags.push(el("span.ticket", null, "主要"));
    if (sense.domain) tags.push(el("span.ticket", { attrs: { title: "领域 / 学科标签" } }, sense.domain));
    if (sense.register) tags.push(el("span.ticket", { attrs: { title: "语域标签" } }, sense.register));
    tags.push(ui.reviewTag(sense.review_status));

    const otherTranslations = (sense.translations || []).filter(
      (t) => t.gloss && t.lang !== "zh" && t.lang !== "en"
    );

    const examples = sense.examples && sense.examples.items ? sense.examples.items : [];

    const exList =
      examples.length || (sense.examples && sense.examples.total)
        ? el(
            "div.ex-list",
            null,
            examples.map((example) => exampleNode(example, words, lang, src)),
            sense.examples.has_more
              ? el(
                  "button.link-btn",
                  {
                    attrs: { type: "button", style: "align-self:flex-start" },
                    onClick: (event) => loadSenseExamples(sense, event.currentTarget, ctx),
                  },
                  `+${sense.examples.total - examples.length} 条例句`
                )
              : null
          )
        : null;

    const foot = el(
      "div.sense__foot",
      null,
      el("span", null, "来源 ", el("span.num", null, sourceName(src, sense.source_id) || "—")),
      sense.confidence != null
        ? el(
            "span",
            { attrs: { title: "来源置信度，启发式分数，不是概率" } },
            "置信度 ",
            el("span.num", null, fmt.conf(sense.confidence))
          )
        : null,
      el(
        "button.link-btn",
        {
          attrs: {
            type: "button",
            style: "margin-left:auto",
            title: "复制一条指向这条义项的链接",
          },
          onClick: () => {
            const url =
              location.origin + location.pathname +
              WH.router.build("entry", { id: entry.lemma_id }, { sense: sense.sense_id });
            WH.copy(url).then((ok) => WH.toast(ok ? "已复制这条义项的链接" : "复制失败"));
          },
        },
        "复制义项链接"
      )
    );

    return el(
      "article.sense" + (isTarget ? ".sense--target" : ""),
      { attrs: { id: "betekenis-" + sense.sense_id } },
      el("div.sense__no", null, String(index + 1).padStart(2, "0")),
      el(
        "div.sense__body",
        null,
        el(
          "div.sense__top",
          null,
          sense.pos ? el("span.ticket", null, sense.pos) : null,
          isTarget ? el("span.ticket.ticket--geel", null, "语义命中") : null,
          tags
        ),
        el("div", null, el("div.gloss-primary", null, WH.withDigraph(gloss || "—"))),
        secondary ? el("div.gloss-secondary", null, secondary) : null,
        sense.definition_nl ? el("p.def-nl", null, sense.definition_nl) : null,
        sense.usage_note
          ? el("p.sense__usage", null, el("b", null, "用法"), sense.usage_note)
          : null,
        otherTranslations.length
          ? el(
              "div.tag-row",
              { style: "margin-top:10px" },
              otherTranslations.map((t) =>
                el("span.ticket", null, t.lang + " · " + t.gloss)
              )
            )
          : null,
        exList,
        foot
      )
    );
  }

  function exampleNode(example, words, lang, src) {
    const translation = WH.exampleTranslation(example, lang);
    return el(
      "div.ex",
      null,
      el("p.ex__nl", null, highlight(example.ex_nl, words)),
      translation ? el("p.ex__tr", null, translation) : null
    );
  }

  function loadSenseExamples(sense, button, ctx) {
    button.setAttribute("aria-disabled", "true");
    button.textContent = "载入中…";
    WH.api
      .examples(sense.sense_id, 0, 20)
      .then((res) => {
        const items = (res.examples && res.examples.items) || [];
        const list = el("div.ex-list");
        items.forEach((example) =>
          list.appendChild(exampleNode(example, ctx.highlightWords, WH.store.state.prefs.glossLang, ctx.sources))
        );
        button.replaceWith(
          el(
            "div",
            { style: "display:grid;gap:10px;margin-top:12px" },
            el(
              "span.micro",
              { style: "color:var(--ink-3)" },
              `${res.examples.total} 条例句 · senses/${sense.sense_id}/examples`
            ),
            list
          )
        );
      })
      .catch((err) => {
        button.removeAttribute("aria-disabled");
        button.textContent = "重试载入例句";
        WH.toast(WH.describeError(err).title);
      });
  }

  function sensesSection(entry, state, ctx, rerender) {
    const items = state.senses.items;
    const filtered = ctx.posFilter
      ? items.filter((s) => {
          const pos = (entry.parts_of_speech || []).find(
            (p) => p.lemma_pos_entry_id === s.lemma_pos_entry_id
          );
          return (pos && pos.app_pos) === ctx.posFilter;
        })
      : items;

    const section = el("section.panel", { attrs: { id: "betekenissen" } });
    section.appendChild(
      el(
        "div.panel__head",
        null,
        el(
          "div.panel__title",
          null,
          el("b", null, "释义"),
          el("span.panel__count", null, `已显示 ${items.length} / ${state.senses.total}`)
        ),
        ctx.posFilter
          ? el(
              "button.link-btn",
              {
                attrs: { type: "button" },
                onClick: () => {
                  ctx.posFilter = null;
                  rerender();
                },
              },
              "清除词性筛选"
            )
          : null
      )
    );

    if (!filtered.length) {
      section.appendChild(
        el("p.sense-empty", null, ctx.posFilter ? "这个词性下当前页没有义项。" : "这个词条还没有义项。")
      );
    } else {
      const list = el("div.senses", ctx.firstDraw ? { dataset: { stagger: "1" } } : null);
      filtered.forEach((sense, i) => {
        const card = senseCard(sense, entry, ctx, i);
        card.style.setProperty("--i", String(i));
        list.appendChild(card);
      });
      section.appendChild(list);
    }

    if (state.senses.has_more) {
      section.appendChild(
        el(
          "div.pager-row",
          null,
          el(
            "span.pager-meta",
            null,
            `sense_offset=${state.senses.next_offset} · limit=${state.senses.limit}`
          ),
          el(
            "button.btn.btn--ghost.btn--sm",
            {
              attrs: {
                type: "button",
                disabled: state.loading.senses,
              },
              onClick: () => loadMore("senses", entry, state, rerender),
            },
            state.loading.senses
              ? WH.motion.spinner("载入中")
              : `加载更多释义（${items.length} / ${state.senses.total}）`
          )
        )
      );
    }
    return section;
  }

  /* ------------------------------------------------------------ corpus ex. -- */

  function corpusSection(entry, state, ctx, rerender) {
    const page = state.corpus;
    const section = el("section.panel", { attrs: { id: "voorbeelden" } });
    section.appendChild(
      el(
        "div.panel__head",
        null,
        el(
          "div.panel__title",
          null,
          el("b", null, "语料例句"),
          el("span.panel__count", null, `${page.items.length} / ${page.total}`)
        ),
        el("span.panel__count", null, "词头级 · 未消歧")
      )
    );

    section.appendChild(
      el(
        "div.corpus-note",
        null,
        icon("alert", { size: 15 }),
        el(
          "div",
          null,
          el("b", null, "未按义项消歧"),
          " · sense_disambiguated = false"
        )
      )
    );

    if (!page.items.length) {
      section.appendChild(el("p.sense-empty", null, "这个词头暂时没有语料例句。"));
      return section;
    }

    const seen = new Map();
    for (const item of page.items) {
      const key = item.ex_nl.trim();
      if (!seen.has(key)) seen.set(key, { item, count: 1 });
      else seen.get(key).count += 1;
    }
    const mergedCount = page.items.length - seen.size;

    const list = el("div.corpus-list");
    const rows = [...seen.values()];
    rows.forEach(({ item, count }) => {
      list.appendChild(
        el(
          "div.corpus-item",
          null,
          el("p", null, highlight(item.ex_nl, ctx.highlightWords)),
          el(
            "div.corpus-item__meta",
            null,
            el("span", null, sourceName(ctx.sources, item.source_id) || "—"),
            el(
              "span",
              { attrs: { title: "例句质量分" } },
              item.quality_score != null ? "q " + fmt.score(item.quality_score) : ""
            ),
            count > 1 ? el("span", { attrs: { title: "同一句挂在多个词性/词形下" } }, count + " 处归属") : null
          )
        )
      );
    });
    section.appendChild(list);
    if (mergedCount > 0) {
      section.appendChild(
        el(
          "p.panel__note",
          { style: "margin-top:10px" },
          `合并了 ${mergedCount} 条重复归属`
        )
      );
    }

    if (page.has_more) {
      section.appendChild(
        el(
          "div.pager-row",
          null,
          el("span.pager-meta", null, `example_offset=${page.next_offset}`),
          el(
            "button.btn.btn--ghost.btn--sm",
            {
              attrs: { type: "button", disabled: state.loading.corpus },
              onClick: () => loadMore("corpus", entry, state, rerender),
            },
            state.loading.corpus
              ? WH.motion.spinner("载入中")
              : `加载更多语料例句（${page.items.length} / ${page.total}）`
          )
        )
      );
    }
    return section;
  }

  /* ---------------------------------------------------------------- forms -- */

  function formsSection(entry, state, ctx, rerender) {
    const lang = WH.store.state.prefs.glossLang;
    const page = state.forms;
    const section = el("section.panel", { attrs: { id: "vormen" } });

    const groups = new Map();
    for (const form of page.items) {
      const key = form.form;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(form);
    }

    let entries = [...groups.entries()];
    if (ctx.formFilter && ctx.formFilter !== "all") {
      entries = entries.filter(([, list]) =>
        list.some((f) => (f.app_form_role || "other") === ctx.formFilter)
      );
    }
    if (ctx.formQuery) {
      const q = ctx.formQuery.toLowerCase();
      entries = entries.filter(([word]) => word.toLowerCase().includes(q));
    }
    entries.sort((a, b) => {
      const canonical = (list) => (list.some((f) => f.is_canonical) ? 0 : 1);
      return canonical(a[1]) - canonical(b[1]) || a[0].localeCompare(b[0], "nl");
    });

    section.appendChild(
      el(
        "div.panel__head",
        null,
        el(
          "div.panel__title",
          null,
          el("b", null, "词形"),
          el("span.panel__count", null, `${page.items.length} / ${page.total} 条`)
        ),
        el("span.panel__count", null, "按词形合并展示")
      )
    );

    section.appendChild(
      el(
        "p.panel__note",
        { style: "margin-bottom:14px" },
        "同名词形已合并，标签为来源。"
      )
    );

    const filters = [
      { key: "all", label: "全部" },
      { key: "canonical", label: "标准词形" },
      { key: "observed_form", label: "语料词形" },
    ];

    section.appendChild(
      el(
        "div.form-tools",
        null,
        filters.map((f) =>
          el(
            "button.chip.chip--plain",
            {
              attrs: { type: "button", "aria-pressed": String((ctx.formFilter || "all") === f.key) },
              onClick: () => {
                ctx.formFilter = f.key;
                rerender();
              },
            },
            f.label
          )
        ),
        el(
          "label.form-search",
          null,
          icon("search", { size: 13 }),
          el("input", {
            attrs: { type: "search", placeholder: "筛选词形", "aria-label": "在词形里找" },
            value: ctx.formQuery || "",
            onInput: WH.debounce((event) => {
              ctx.formQuery = event.target.value.trim();
              rerender({ keepFocus: "form-search" });
            }, 220),
          })
        ),
        el("span.panel__count", { style: "margin-left:auto" }, `${entries.length} 个词形`)
      )
    );

    if (!entries.length) {
      section.appendChild(el("p.sense-empty", null, "没有符合条件的词形。"));
    } else {
      const grid = el("div.form-grid");
      for (const [word, list] of entries) {
        const roles = [...new Set(list.map((f) => WH.formLabel(f, lang)))].filter(Boolean);
        const flags = [
          ...new Set(
            list
              .map((f) => {
                if (f.is_canonical) return "canonical";
                if (f.is_observed) return "observed";
                return f.app_form_role || "other";
              })
              .filter(Boolean)
          ),
        ];
        const item = el(
          "button.form-item",
          {
            attrs: {
              type: "button",
              title: `复制 ${word}`,
            },
            onClick: async () => {
              const ok = await WH.copy(word);
              WH.toast(ok ? "已复制：" + word : "复制失败");
            },
          },
          el("span.form-item__copy", null, "复制"),
          el(
            "span.form-item__word",
            null,
            word,
            list.length > 1 ? el("i", null, "×" + list.length) : null
          ),
          el(
            "span.form-item__meta",
            null,
            roles.slice(0, 2).map((r) => el("span", null, r)),
            flags.includes("observed") ? el("span", null, "语料") : null
          )
        );
        grid.appendChild(item);
      }
      section.appendChild(grid);
    }

    if (page.has_more) {
      section.appendChild(
        el(
          "div.pager-row",
          null,
          el("span.pager-meta", null, `form_offset=${page.next_offset}`),
          el(
            "button.btn.btn--ghost.btn--sm",
            {
              attrs: { type: "button", disabled: state.loading.forms },
              onClick: () => loadMore("forms", entry, state, ctx.rerender || rerender),
            },
            state.loading.forms
              ? WH.motion.spinner("载入中")
              : `加载更多词形（${page.items.length} / ${page.total}）`
          )
        )
      );
    }
    return section;
  }

  /* ---------------------------------------------------------- expressions -- */

  function expressionsSection(entry, state, ctx) {
    const lang = WH.store.state.prefs.glossLang;
    const page = state.expressions;
    const section = el("section.panel", { attrs: { id: "uitdrukkingen" } });
    section.appendChild(
      el(
        "div.panel__head",
        null,
        el(
          "div.panel__title",
          null,
          el("b", null, "表达与构式"),
          el("span.panel__count", null, fmt.num(page.total) + " 条")
        ),
        el("span.panel__count", null, "按 entry_kind 分四类")
      )
    );

    if (!page.items.length) {
      section.appendChild(
        el(
          "p.sense-empty",
          null,
          "无记录。"
        )
      );
      return section;
    }

    const kinds = ["lexical_expression", "usage_construction", "definition_note", "usage_example"];
    for (const kind of kinds) {
      const items = page.items.filter((x) => x.entry_kind === kind);
      if (!items.length) continue;
      const group = el("div.expr-group");
      group.appendChild(
        el(
          "div.expr-kind",
          null,
          el("h3", null, WH.labels.kind[kind] || kind),
          el("span.panel__count", null, WH.labels.kindDesc[kind] || "")
        )
      );
      items.forEach((expr) => {
        const gloss =
          lang === "zh" ? expr.gloss_zh : lang === "en" ? expr.gloss_en : expr.gloss_en;
        const explanation =
          lang === "zh" ? expr.explanation_zh : lang === "en" ? expr.explanation_en : "";
        group.appendChild(
          el(
            "article.expr",
            null,
            el(
              "div.expr__head",
              null,
              el("span.expr__nl", null, WH.withDigraph(expr.expression_nl)),
              gloss ? el("span.expr__gloss", null, gloss) : null,
              ui.reviewTag(expr.review_status)
            ),
            expr.definition_nl ? el("p.expr__def", null, expr.definition_nl) : null,
            explanation ? el("p.expr__def", { style: "color:var(--ink-3)" }, explanation) : null,
            expr.example_nl
              ? el(
                  "p.expr__ex",
                  null,
                  expr.example_nl,
                  expr.example_zh && lang !== "en" ? el("span", null, expr.example_zh) : null
                )
              : null,
            expr.usage_note ? el("p.expr__note", null, expr.usage_note) : null
          )
        );
      });
      section.appendChild(group);
    }
    return section;
  }

  /* -------------------------------------------------------------- sources -- */

  function sourcesSection(entry) {
    const section = el("section.panel", { attrs: { id: "bronnen" } });
    section.appendChild(
      el(
        "div.panel__head",
        null,
        el(
          "div.panel__title",
          null,
          el("b", null, "来源与许可"),
          el("span.panel__count", null, entry.sources.length + " 个")
        ),
        el("span.panel__count", null, "同一条数据只列一次")
      )
    );
    section.appendChild(
      el(
        "p.panel__note",
        { style: "margin-bottom:18px" },
        "许可、署名、版本按接口返回显示。"
      )
    );
    const list = el("div.source-list");
    for (const source of entry.sources) {
      list.appendChild(
        el(
          "div.source",
          null,
          el(
            "div.source__name",
            null,
            el("b", null, source.name),
            source.attribution ? el("span.source__attr", null, source.attribution) : null
          ),
          el(
            "div.source__meta",
            null,
            el("span", null, WH.labels.sourceType[source.source_type] || source.source_type),
            source.license ? el("span", null, source.license) : el("span", null, "许可见文"),
            source.version ? el("span", null, "v" + source.version) : null
          ),
          source.url
            ? el(
                "a.btn.btn--quiet.btn--sm",
                { href: source.url, attrs: { target: "_blank", rel: "noopener noreferrer" } },
                "来源页",
                icon("external", { size: 12 })
              )
            : el("span.panel__count", null, "无链接")
        )
      );
    }
    section.appendChild(list);
    return section;
  }

  /* ------------------------------------------------------------------ rail -- */

  function rail(entry, state, ctx, rerender) {
    const lang = WH.store.state.prefs.glossLang;
    const cards = [];

    if (entry.word_family) {
      cards.push(
        el(
          "div.card.card--rail",
          null,
          el("div.card__head", null, el("span.card__title", null, "词族")),
          el(
            "div.family-link",
            null,
            el("span.word", null, WH.withDigraph(entry.word_family)),
            entry.family_head_lemma_id && entry.family_head_lemma_id !== entry.lemma_id
              ? el(
                  "a.link-btn",
                  { href: WH.router.build("entry", { id: entry.family_head_lemma_id }) },
                  "词族中心"
                )
              : el("span.panel__count", null, "本身即中心")
          ),
          el("p.panel__note", { style: "margin-top:8px" }, "无成员列表，需逐个查。")
        )
      );
    }

    /* transparency: a first-class citizen, not a footnote */
    const senses = state.senses.items;
    const loaded = senses.length;
    const total = state.senses.total;
    const counts = { accepted: 0, needs_review: 0, unreviewed: 0 };
    for (const sense of senses) counts[sense.review_status] = (counts[sense.review_status] || 0) + 1;
    const reviewed = counts.accepted;
    const posNeeds = (entry.parts_of_speech || []).filter((p) => p.needs_review).length;
    const formNeeds = state.forms.items.filter((f) => f.needs_review).length;

    cards.push(
      el(
        "div.card.card--rail",
        null,
        el(
          "div.card__head",
          null,
          el("span.card__title", null, "标注透明"),
          el(
            "button.link-btn.text-xs",
            { attrs: { type: "button" }, onClick: () => WH.router.go("about") },
            "怎么看"
          )
        ),
        el(
          "p.panel__count",
          { style: "margin:-4px 0 10px" },
          loaded === total ? `全部 ${total} 条义项` : `已加载 ${loaded} / ${total} 条义项`
        ),
        el(
          "div.bar",
          { attrs: { "aria-hidden": "true" }, style: "margin-bottom:12px" },
          reviewed ? el("i", { style: `width:${(reviewed / (loaded || 1)) * 100}%;background:var(--groen)` }) : null,
          counts.needs_review
            ? el("i", { style: `width:${(counts.needs_review / (loaded || 1)) * 100}%;background:var(--geel)` })
            : null,
          counts.unreviewed
            ? el(
                "i",
                { style: `width:${(counts.unreviewed / (loaded || 1)) * 100}%;background:var(--ink-3);opacity:.55` }
              )
            : null
        ),
        el(
          "div.transparency",
          null,
          el(
            "div.trow",
            null,
            el("i.dot.dot--ok"),
            el("span", null, "已审核"),
            el("span.num", null, counts.accepted + " / " + loaded)
          ),
          el(
            "div.trow",
            null,
            el("i.dot.dot--warn"),
            el("span", null, "待复核"),
            el("span.num", null, counts.needs_review)
          ),
          el(
            "div.trow",
            null,
            el("i.dot.dot--bad"),
            el("span", null, "未复核"),
            el("span.num", null, counts.unreviewed)
          ),
          el(
            "div.trow",
            { style: "margin-top:6px" },
            el("i.dot"),
            el("span", null, "词性 / 词形待复核"),
            el("span.num", null, posNeeds + " / " + formNeeds)
          )
        ),
        el("p.panel__note", { style: "margin-top:10px" }, "置信度是启发式分数，非概率。")
      )
    );

    /* contextual language notes, derived from the entry's own forms */
    const allForms = state.forms.items;
    const separable = detectSeparable(entry.lemma, allForms);
    const notes = [];
    if (WH.includesIj(entry.lemma)) {
      notes.push({
        title: "含 IJ",
        text: "词首两字母一起大写。",
        evidence: entry.lemma,
      });
    }
    if (separable) {
      notes.push({
        title: "像可分动词",
        text: `以 ${separable.prefix}- 开头，词形有 ${separable.evidence
          .map((e) => "「" + e + "」")
          .join("、")}。词形推断，非接口字段。`,
        evidence: "scheidbaar",
      });
    }
    if ((entry.lemma || "").match(/(je|tje|pje|etje|kje)$/i)) {
      notes.push({
        title: "可能是指小词",
        text: "-je / -tje 指小后缀。",
        evidence: entry.lemma,
      });
    }
    if (notes.length) {
      cards.push(
        el(
          "div.card.card--rail",
          null,
          el("div.card__head", null, el("span.card__title", null, "语言指南 · 本词"),
            el("button.link-btn.text-xs", { attrs: { type: "button" }, onClick: () => ui.openGuide() }, "全部")
          ),
          notes.map((note) =>
            el(
              "div",
              { style: "margin-bottom:14px" },
              el("div", { style: "font-size:var(--fs-sm);font-weight:500;margin-bottom:3px" }, note.title),
              el("p.panel__note", null, note.text)
            )
          )
        )
      );
    }

    cards.push(
      el(
        "div.card.card--rail",
        null,
        el("div.card__head", null, el("span.card__title", null, "释义显示")),
        el(
          "div.chips",
          null,
          [
            ["zh", "中文"],
            ["en", "English"],
            ["nl", "Nederlands"],
          ].map(([key, label]) =>
            el(
              "button.chip",
              {
                attrs: { type: "button", "aria-pressed": String(lang === key) },
                onClick: () => {
                  WH.store.setGlossLang(key);
                  rerender();
                },
              },
              label
            )
          )
        ),
        el("p.panel__note", { style: "margin-top:10px" }, "荷兰语原释义始终保留。")
      )
    );

    return el("aside.rail.rail-sticky", null, cards);
  }

  /* ------------------------------------------------------------- pagination -- */

  function loadMore(group, entry, state, rerender) {
    const page = state[group];
    if (!page.has_more || state.loading[group]) return;
    state.loading[group] = true;
    rerender();
    const params = {};
    params[PARAM[group][0]] = page.next_offset;
    params[PARAM[group][1]] = page.limit || PAGE[group];
    WH.api
      .entry(entry.lemma_id, params)
      .then((res) => {
        const next = res[GROUP_KEY[group]];
        const current = state[group];
        const idKey = PARAM[group][2];
        const seen = new Set(current.items.map((x) => x[idKey]));
        const merged = current.items.concat(next.items.filter((x) => !seen.has(x[idKey])));
        state[group] = {
          items: merged,
          total: next.total,
          offset: 0,
          limit: next.limit,
          has_more: next.has_more,
          next_offset: next.next_offset,
        };
        state.loading[group] = false;
        // other groups in this response are page one — deliberately ignored
        rerender();
      })
      .catch((err) => {
        state.loading[group] = false;
        WH.toast(WH.describeError(err).title);
        const info = WH.describeError(err);
        state.error = { group, info };
        rerender();
      });
  }

  /* ------------------------------------------------------------------ view -- */

  WH.views = WH.views || {};

  WH.views.entry = function (route, mount) {
    const lemmaId = Number(route.params.id);
    const wrap = el("div");
    wrap.appendChild(ui.skeletonEntry());
    mount(wrap);

    const controller = new AbortController();
    let cancelled = false;
    let cleanupScrollSpy = null;

    const ctx = {
      posFilter: null,
      formFilter: "all",
      formQuery: "",
      targetSenseId: route.query.sense ? Number(route.query.sense) : null,
      firstDraw: true,
      highlightWords: [],
      sources: new Map(),
      rerender: null,
    };

    WH.api
      .entry(lemmaId, {}, controller.signal)
      .then((entry) => {
        if (cancelled) return;
        ctx.sources = sourceMap(entry.sources);
        WH.cache.lastEntry = entry;

        const state = {
          senses: entry.senses,
          forms: entry.forms,
          corpus: entry.corpus_examples,
          expressions: entry.expressions,
          loading: {},
          error: null,
        };

        // highlight every form that is spelled like the headword family
        const words = new Set([entry.lemma]);
        for (const form of entry.forms.items) {
          if (form.form && form.form.length > 2 && form.form.length <= entry.lemma.length + 3) {
            words.add(form.form);
          }
        }
        ctx.highlightWords = [...words];
        ctx.entry = entry;

        const rerender = (opts = {}) => {
          const scrollY = window.scrollY;
          const active = document.activeElement;
          const wasFormSearch = active && active.getAttribute && active.getAttribute("type") === "search";
          const caret = wasFormSearch ? active.selectionStart : null;
          draw();
          if (opts.keepFocus || wasFormSearch) {
            const input = wrap.querySelector(".form-search input");
            if (input) {
              input.focus();
              if (caret != null) {
                try {
                  input.setSelectionRange(caret, caret);
                } catch (e) {
                  /* search inputs may not support selection */
                }
              }
            }
          } else {
            window.scrollTo({ top: scrollY, behavior: "auto" });
          }
        };
        ctx.rerender = rerender;

        function draw() {
          wrap.replaceChildren();
          const lang = WH.store.state.prefs.glossLang;
          const top = el(
            "div",
            null,
            el(
              "div.wrap",
              null,
              el(
                "nav.breadcrumb",
                { attrs: { "aria-label": "面包屑" } },
                el("a", { href: WH.router.build("home") }, "查词"),
                el("span.sep", null, "/"),
                route.query.q
                  ? el(
                      "a",
                      {
                        href: WH.router.build("lookup", {}, { q: route.query.q }),
                      },
                      "「" + route.query.q + "」"
                    )
                  : el("span", null, "词条"),
                el("span.sep", null, "/"),
                el("span", null, entry.lemma)
              ),
              headBlock(entry, route, ctx)
            )
          );

          const sections = [
            { id: "betekenissen", label: "释义", count: state.senses.total },
            { id: "voorbeelden", label: "语料例句", count: state.corpus.total },
            { id: "vormen", label: "词形", count: state.forms.total },
            { id: "uitdrukkingen", label: "表达", count: state.expressions.total },
            { id: "bronnen", label: "来源", count: entry.sources.length },
          ];
          const subnav = el(
            "nav.subnav",
            { attrs: { "aria-label": "词条内导航" } },
            el(
              "div.wrap.subnav__inner",
              null,
              sections.map((s, i) =>
                el(
                  "a" + (i === 0 ? ".is-current" : ""),
                  { href: "#" + s.id, dataset: { target: s.id } },
                  s.label,
                  el("span.num", null, fmt.num(s.count))
                )
              )
            )
          );
          subnav.addEventListener("click", (event) => {
            const link = event.target.closest("a[data-target]");
            if (!link) return;
            event.preventDefault();
            const target = document.getElementById(link.dataset.target);
            if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
          });

          const posNav = el(
            "div.pos-nav",
            { style: "padding-block:14px" },
            el(
              "button.pos-pill",
              {
                attrs: { type: "button", "aria-pressed": String(!ctx.posFilter) },
                onClick: () => {
                  ctx.posFilter = null;
                  rerender();
                },
              },
              "全部",
              el("small", null, state.senses.total)
            ),
            dedupePos(entry.parts_of_speech).map((pos) =>
              el(
                "button.pos-pill",
                {
                  attrs: {
                    type: "button",
                    "aria-pressed": String(ctx.posFilter === (pos.app_pos || pos.pos)),
                    title: pos.pos + (pos.is_primary ? " · 主要词性" : ""),
                  },
                  onClick: () => {
                    const key = pos.app_pos || pos.pos;
                    ctx.posFilter = ctx.posFilter === key ? null : key;
                    rerender();
                  },
                },
                WH.posLabel(pos, lang),
                el("small", null, (pos.sources || [pos.pos]).join(" / "))
              )
            )
          );

          const main = el(
            "div",
            null,
            sensesSection(entry, state, ctx, rerender),
            state.error
              ? el(
                  "div.notice.notice--warn",
                  { style: "margin-block:16px" },
                  icon("alert", { size: 15 }),
                  el(
                    "div",
                    null,
                    el("b", null, WH.describeError(state.error.info).title),
                    " " + WH.describeError(state.error.info).text
                  )
                )
              : null,
            corpusSection(entry, state, ctx, rerender),
            formsSection(entry, state, ctx, rerender),
            expressionsSection(entry, state, ctx),
            sourcesSection(entry)
          );

          wrap.appendChild(top);
          wrap.appendChild(subnav);
          wrap.appendChild(
            el(
              "div.wrap",
              null,
              posNav,
              el("div.two-col", null, main, rail(entry, state, ctx, rerender))
            )
          );

          cleanupScrollSpy && cleanupScrollSpy();
          cleanupScrollSpy = setupScrollSpy(sections.map((s) => s.id));
          ctx.firstDraw = false;

          if (route.query.to) {
            const target = document.getElementById(route.query.to);
            if (target) {
              requestAnimationFrame(() => {
                target.scrollIntoView({ behavior: "smooth", block: "start" });
              });
            }
          }
        }

        document.title =
          (entry.display_lemma || entry.lemma) + " — woordhuis";
        draw();
        mountCleanup = () => {
          cleanupScrollSpy && cleanupScrollSpy();
        };

        // semantic entry: the matched sense may live on a later page
        if (ctx.targetSenseId) {
          const has = state.senses.items.some(
            (s) => Number(s.sense_id) === Number(ctx.targetSenseId)
          );
          if (!has && state.senses.has_more) {
            chaseTargetSense(entry, state, ctx, rerender, 0);
          } else if (has) {
            requestAnimationFrame(() => {
              const node = document.getElementById("betekenis-" + ctx.targetSenseId);
              if (node) node.scrollIntoView({ behavior: "smooth", block: "center" });
            });
          }
        }
      })
      .catch((err) => {
        if (cancelled || err.kind === "aborted") return;
        wrap.replaceChildren();
        wrap.appendChild(
          el(
            "div.wrap",
            null,
            el(
              "nav.breadcrumb",
              { attrs: { "aria-label": "面包屑" } },
              el("a", { href: WH.router.build("home") }, "查词"),
              el("span.sep", null, "/"),
              el("span", null, "词条 " + lemmaId)
            ),
            notFoundOrError(err, lemmaId)
          )
        );
      });

    let mountCleanup = null;

    return function cleanup() {
      cancelled = true;
      controller.abort();
      mountCleanup && mountCleanup();
    };
  };

  function chaseTargetSense(entry, state, ctx, rerender, depth) {
    if (depth > 3 || !state.senses.has_more) return;
    WH.api
      .entry(entry.lemma_id, {
        sense_offset: state.senses.next_offset,
        sense_limit: state.senses.limit,
      })
      .then((res) => {
        const next = res.senses;
        const seen = new Set(state.senses.items.map((s) => s.sense_id));
        state.senses = {
          items: state.senses.items.concat(next.items.filter((s) => !seen.has(s.sense_id))),
          total: next.total,
          offset: 0,
          limit: next.limit,
          has_more: next.has_more,
          next_offset: next.next_offset,
        };
        const found = state.senses.items.some(
          (s) => Number(s.sense_id) === Number(ctx.targetSenseId)
        );
        rerender();
        if (found || !state.senses.has_more) {
          requestAnimationFrame(() => {
            const node = document.getElementById("betekenis-" + ctx.targetSenseId);
            if (node) node.scrollIntoView({ behavior: "smooth", block: "center" });
          });
        } else {
          chaseTargetSense(entry, state, ctx, rerender, depth + 1);
        }
      })
      .catch(() => {
        /* keep the first page; the banner already explains the target sense */
      });
  }

  function setupScrollSpy(ids) {
    const links = new Map();
    document.querySelectorAll(".subnav a[data-target]").forEach((a) => links.set(a.dataset.target, a));
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const link = links.get(entry.target.id);
          if (!link) continue;
          links.forEach((a) => a.classList.remove("is-current"));
          link.classList.add("is-current");
        }
      },
      { rootMargin: "-20% 0px -70% 0px", threshold: 0 }
    );
    for (const id of ids) {
      const node = document.getElementById(id);
      if (node) observer.observe(node);
    }
    return () => observer.disconnect();
  }

  /* -------------------------------------------------------- unavailable -- */

  function notFoundOrError(err, lemmaId) {
    const info = WH.describeError(err);
    if (err.status !== 404 && err.status !== 501) return ui.errorPanel(err, {});

    const cached = WH.cache.semanticByLemma && WH.cache.semanticByLemma.get(Number(lemmaId));
    const recorded = [
      { id: 138, lemma: "huis" },
      { id: 1, lemma: "zijn" },
      { id: 8, lemma: "hebben" },
      { id: 21, lemma: "kunnen" },
      { id: 34, lemma: "komen" },
      { id: 36, lemma: "goed" },
      { id: 44, lemma: "zeggen" },
      { id: 51, lemma: "zien" },
      { id: 2327, lemma: "afzetten" },
      { id: 662, lemma: "ontdekken" },
    ];

    const chips = el(
      "div",
      { style: "margin-top:6px" },
      el("span.eyebrow", null, "本包可用的词条"),
      el(
        "div.chips",
        { style: "margin-top:10px" },
        recorded.map((r) => el("a.chip", { href: WH.router.build("entry", { id: r.id }) }, r.lemma))
      )
    );

    const cachedCard = cached
      ? el(
          "div.card",
          { style: "margin-top:26px;max-width:560px" },
          el("div.card__head", null, el("span.card__title", null, "搜索时匹配到的义项")),
          el("div.gloss-primary", null, cached.matched_sense.translation_zh || cached.lemma),
          el("p.def-nl", null, cached.matched_sense.definition_nl || ""),
          el(
            "p.panel__note",
            { style: "margin-top:10px" },
            "来自上一次语义检索，非完整词条。"
          )
        )
      : null;

    return el(
      "div",
      null,
      ui.state({
        code: info.code,
        title: info.kind === "not_recorded" ? "词条未录制" : info.title,
        text:
          info.kind === "not_recorded"
            ? `离线包只有 ${recorded.length} 个完整词条。`
            : info.text,
        iconName: "windmill",
        actions: [
          el("a.btn.btn--primary", { href: WH.router.build("home") }, "回到查词"),
          el(
            "button.btn.btn--ghost",
            { attrs: { type: "button" }, onClick: () => WH.router.go("saved") },
            "我的词库"
          ),
        ],
      }),
      chips,
      cachedCard
    );
  }
})();
