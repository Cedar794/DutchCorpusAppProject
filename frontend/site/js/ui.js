/* ==========================================================================
   Woordhuis · ui
   Shared components: header, footer, search combobox, tiles, states, inspector.
   ========================================================================== */
(function () {
  "use strict";

  const WH = (window.WH = window.WH || {});
  const { el, icon, fmt, copy, toast, debounce } = WH;
  const { state } = WH.store;
  const ui = (WH.ui = {});

  const COMMON_SUGGEST_CACHE = new Map();

  /* ------------------------------------------------------------ fragments -- */

  ui.levelTicket = function (level, title) {
    return el(
      "span.ticket.ticket--lvl.ticket--lvl-" + (level || 4),
      { attrs: { title: title || "项目分级 1–4（不是 CEFR）" } },
      fmt.level(level)
    );
  };

  ui.reviewTag = function (status) {
    const map = {
      accepted: ["dot--ok", WH.labels.review.accepted],
      needs_review: ["dot--warn", WH.labels.review.needs_review],
      unreviewed: ["dot--bad", WH.labels.review.unreviewed],
    };
    const [dotClass, text] = map[status] || ["", status || "—"];
    return el("span.status-line", null, el("i.dot." + dotClass), text);
  };

  ui.digraph = function (word, className) {
    const holder = el(className ? className : "span");
    holder.appendChild(WH.withDigraph(word));
    return holder;
  };

  ui.copyButton = function (text, label, opts = {}) {
    const button = el(
      "button.btn.btn--quiet.btn--sm",
      {
        attrs: { type: "button", title: "复制" },
        onClick: async () => {
          const ok = await copy(text);
          toast(ok ? (opts.toast || "已复制：" + text) : "复制失败，请手动选择");
          if (!ok) return;
          const mark = icon("check", { size: 13 });
          button.replaceChildren(mark, el("span", null, "已复制"));
          button.classList.add("is-done");
          setTimeout(() => {
            button.classList.remove("is-done");
            button.replaceChildren(icon("copy", { size: 13 }), el("span", null, label || "复制"));
          }, 1400);
        },
      },
      icon("copy", { size: 13 }),
      el("span", null, label || "复制")
    );
    return button;
  };

  /* --------------------------------------------------------------- header -- */

  ui.header = function () {

    const navLink = (name, label, path) => {
      const current = WH.router.current();
      const isCurrent =
        (name === "home" && current.name === "home") ||
        (name !== "home" && current.path && current.path.startsWith(path));
      return el(
        "a",
        {
          href: WH.router.build(name),
          attrs: isCurrent ? { "aria-current": "page" } : {},
        },
        label
      );
    };

    const logo = el(
      "a.logo",
      { href: WH.router.build("home"), attrs: { "aria-label": "Woordhuis 首页" } },
      icon("gable", { size: 26, class: "logo__mark" }),
      el(
        "span",
        null,
        el("span.logo__word", null, "woordhuis"),
        el("span.logo__sub", null, "NL · 词之屋")
      )
    );

    const glowBtn = el(
      "button.icon-btn",
      {
        attrs: { type: "button", "aria-label": "释义显示语言：中文 / English / Nederlands" },
        title: "切换释义语言（中文 / English / Nederlands）",
        onClick: () => {
          const order = ["zh", "en", "nl"];
          const next = order[(order.indexOf(state.prefs.glossLang) + 1) % order.length];
          WH.store.setGlossLang(next);
          toast("释义显示：" + { zh: "中文", en: "English", nl: "Nederlands" }[next]);
        },
      },
      el("span.mono", { style: "font-size:10px;letter-spacing:.08em" },
        state.prefs.glossLang === "zh" ? "中" : state.prefs.glossLang === "en" ? "EN" : "NL")
    );

    const themeBtn = el(
      "button.icon-btn",
      {
        attrs: { type: "button", "aria-label": "切换明暗" },
        title: "明暗切换（Delfts blauw / Nachtblauw）",
        onClick: (event) => WH.motion.toggleTheme(event),
      },
      icon(state.prefs.theme === "nacht" ? "sun" : "moon", { size: 17 })
    );

    return el(
      "header.site-header",
      null,
      el(
        "div.site-header__inner",
        null,
        logo,
        el(
          "nav.nav",
          { attrs: { "aria-label": "主导航" } },
          navLink("home", "查词", "/"),
          navLink("saved", "我的词库", "/woordenschat"),
          navLink("about", "数据与方法", "/over")
        ),
        el(
          "div.header-actions",
          null,
          el(
            "button.icon-btn",
            {
              attrs: { type: "button", "aria-label": "搜索（⌘K）" },
              title: "搜索（⌘K 或 /）",
              onClick: () => WH.app.focusSearch(),
            },
            icon("search", { size: 17 })
          ),
          glowBtn,
          themeBtn
        )
      )
    );
  };

  /* --------------------------------------------------------------- footer -- */

  ui.footer = function () {
    const recorded = WH.api.recordedAt ? WH.api.recordedAt() : null;
    return el(
      "footer.site-footer",
      null,
      el(
        "div.wrap",
        null,
        el(
          "div.footer-grid",
          null,
          el(
            "div",
            null,
            el("p.footer-motto", null, "Al doende leert men."),
            el(
              "p.footer-note",
              null,
              WH.api.mode === "http"
                ? "在线接口 · " + (WH.api.base || location.origin)
                : "离线回放 · " + (recorded ? fmt.date(recorded) : "2026-10-23") + " 录制的 69 条响应"
            )
          ),
          el(
            "div.footer-col",
            null,
            el("h3", null, "导航"),
            el(
              "ul",
              null,
              el("li", null, el("a", { href: WH.router.build("home") }, "查词")),
              el("li", null, el("a", { href: WH.router.build("saved") }, "我的词库")),
              el("li", null, el("a", { href: WH.router.build("about") }, "数据与方法"))
            )
          ),
          el(
            "div.footer-col",
            null,
            el("h3", null, "数据"),
            el(
              "ul",
              null,
              el("li", null, el("span.text-sm.muted", null, "Open Dutch WordNet · CC BY-SA 4.0")),
              el("li", null, el("span.text-sm.muted", null, "DBnary · CC BY-SA 3.0")),
              el("li", null, el("span.text-sm.muted", null, "SUBTLEX-NL · 来源限定")),
              el("li", null, el("span.text-sm.muted", null, "字体 OFL · 图形手绘"))
            )
          )
        ),
        el(
          "div.footer-base",
          null,
          el("span", null, "合同 2026-10-23"),
          el("span", null, "woorhuis v1.0")
        )
      )
    );
  };

  /* --------------------------------------------------------------- search -- */

  /**
   * @param {object} opts
   *  mode: 'lookup' | 'semantic'
   *  value: string
   *  variant: 'hero' | 'compact'
   *  onSubmit(mode, query)
   *  onModeChange(mode)
   */
  ui.search = function (opts = {}) {
    const mode = opts.mode || "lookup";
    const id = "q-" + Math.random().toString(36).slice(2, 7);
    let activeIndex = -1;
    let items = [];
    let controller = null;
    let seq = 0;

    const input = el("input.search__input", {
      attrs: {
        id,
        type: "text",
        name: "q",
        autocomplete: "off",
        autocapitalize: "off",
        spellcheck: "false",
        role: "combobox",
        "aria-autocomplete": "list",
        "aria-expanded": "false",
        "aria-controls": id + "-list",
        placeholder:
          mode === "lookup"
            ? "输入荷兰语词或词形，如 huizen、afzetten"
            : "用中文、英文或荷兰语描述你要找的意思",
      },
      value: opts.value || "",
    });

    const list = el("div.suggest", {
      attrs: { id: id + "-list", role: "listbox", hidden: true },
    });

    const prefix = el("span.search__prefix", null, mode === "lookup" ? "NL" : "NL · 中 · EN");

    const submitLabel = mode === "lookup" ? "查找" : "按意思搜索";
    const submit = el(
      "button.search__submit",
      { attrs: { type: "submit" } },
      el("span.long", null, submitLabel),
      el("span.short", null, mode === "lookup" ? "查" : "搜"),
      icon("arrowRight", { size: 16 })
    );

    const row = el("div.search__row", null, prefix, el("div.search__field", null, input, list), submit);

    const tabs = el(
      "div.search__tabs",
      { attrs: { role: "tablist", "aria-label": "查询方式" } },
      tabButton("lookup", "查词", "WOORD"),
      tabButton("semantic", "按意思找词", "BETEKENIS")
    );

    function tabButton(value, label, code) {
      return el(
        "button.search__tab",
        {
          attrs: {
            type: "button",
            role: "tab",
            "aria-selected": String(mode === value),
          },
          onClick: () => {
            if (mode === value) return;
            if (opts.onModeChange) opts.onModeChange(value, input.value);
            else WH.router.go(value, {}, { q: input.value.trim() });
          },
        },
        el("b", null, label),
        el("span", null, code)
      );
    }

    const hints =
      mode === "lookup"
        ? el(
            "div.search__hint",
            null,
            el("span", null, el("kbd.kbd", null, "↵"), " 查词"),
            el("span", null, el("kbd.kbd", null, "↑"), el("kbd.kbd", null, "↓"), " 选候选"),
            el(
              "span",
              null,
              "按意思找词则是 ",
              el(
                "button.link-btn",
                {
                  attrs: { type: "button" },
                  onClick: () => WH.router.go("semantic", {}, { q: input.value.trim() }),
                },
                "另一条链路"
              )
            )
          )
        : el(
            "div.search__hint",
            null,
            el(
              "span",
              null,
              "每次提交都会调用一次模型改写 + 向量检索；不会跟着打字实时触发。"
            ),
            el("span", null, "语义额度比查词更紧：10 次/分钟。")
          );

    function setActive(index) {
      const rows = Array.from(list.querySelectorAll(".suggest__row"));
      if (!rows.length) return;
      activeIndex = (index + rows.length) % rows.length;
      rows.forEach((row, i) => {
        row.setAttribute("aria-selected", String(i === activeIndex));
      });
      input.setAttribute("aria-activedescendant", rows[activeIndex].id);
      rows[activeIndex].scrollIntoView({ block: "nearest" });
    }

    function close() {
      list.hidden = true;
      list.replaceChildren();
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      activeIndex = -1;
    }

    function renderSuggestions(query, suggestions) {
      items = suggestions;
      list.replaceChildren();
      if (!suggestions.length) {
        list.appendChild(
          el("div.suggest__empty", null, `没有以「${query}」开头的词头。按 ↵ 仍然可以完整查一次。`)
        );
      } else {
        suggestions.forEach((s, i) => {
          const row = el(
            "button.suggest__row",
            {
              attrs: { type: "button", role: "option", id: id + "-opt-" + i, "aria-selected": "false" },
              onClick: () => {
                WH.store.addRecent(s.lemma, "lookup");
                Go.entry(s.lemma_id, { q: query, form: s.form || "", mt: s.match_type });
              },
              onMouseenter: () => {
                activeIndex = i;
                Array.from(list.querySelectorAll(".suggest__row")).forEach((r, j) =>
                  r.setAttribute("aria-selected", String(j === i))
                );
                input.setAttribute("aria-activedescendant", id + "-opt-" + i);
              },
            },
            s.form && s.form !== s.lemma
              ? el("span.suggest__form", null, "词形")
              : el("span", { style: "width:0" }),
            el(
              "span",
              null,
              el("span.suggest__word", null, WH.withDigraph(s.lemma)),
              el(
                "span.suggest__meta",
                { style: "display:block;margin-top:2px" },
                [
                  s.form && s.form !== s.lemma ? s.form : null,
                  WH.labels.match[s.match_type] || s.match_type,
                  s.level ? "L" + s.level : null,
                ]
                  .filter(Boolean)
                  .join(" · ")
              )
            ),
            icon("arrowRight", { size: 14 })
          );
          list.appendChild(row);
        });
        list.appendChild(
          el(
            "div.suggest__foot",
            null,
            el("span", null, "↑↓ 选择"),
            el("span", null, "↵ 打开词条"),
            el("span", null, "Esc 关闭")
          )
        );
      }
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      activeIndex = -1;
      positionList();
    }

    function positionList() {
      if (list.hidden) return;
      const rect = row.getBoundingClientRect();
      const below = window.innerHeight - rect.bottom - 18;
      const above = rect.top - 18;
      const flip = below < 260 && above > below;
      list.classList.toggle("suggest--up", flip);
      list.style.top = flip ? "auto" : "100%";
      list.style.bottom = flip ? "100%" : "auto";
      list.style.maxHeight = Math.min(flip ? above : below, 460) + "px";
    }

    const onViewportChange = () => positionList();
    window.addEventListener("resize", onViewportChange);

    function fetchSuggestions(query) {
      if (mode !== "lookup" || query.length < 2) {
        close();
        return;
      }
      if (COMMON_SUGGEST_CACHE.has(query)) {
        renderSuggestions(query, COMMON_SUGGEST_CACHE.get(query));
        return;
      }
      if (controller) controller.abort();
      controller = new AbortController();
      const mine = ++seq;
      WH.api
        .suggest(query, controller.signal)
        .then((res) => {
          if (mine !== seq) return;
          const suggestions = res.suggestions || [];
          COMMON_SUGGEST_CACHE.set(query, suggestions);
          if (document.activeElement === input) renderSuggestions(query, suggestions);
        })
        .catch((err) => {
          if (mine !== seq || err.kind === "aborted") return;
          if (err.status === 429) {
            list.replaceChildren(
              el(
                "div.suggest__empty",
                null,
                "联想请求已受限流（429）。稍等再试，或直接按 ↵ 查一次。"
              )
            );
            list.hidden = false;
            input.setAttribute("aria-expanded", "true");
          } else {
            close();
          }
        });
    }

    const debounced = debounce(fetchSuggestions, 320);

    input.addEventListener("input", () => {
      const value = input.value.trim();
      if (!value) close();
      debounced(value);
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (list.hidden) return;
        setActive(activeIndex + 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        if (list.hidden) return;
        setActive(activeIndex - 1);
      } else if (event.key === "Enter") {
        if (activeIndex >= 0 && items[activeIndex]) {
          event.preventDefault();
          const s = items[activeIndex];
          WH.store.addRecent(s.lemma, "lookup");
          Go.entry(s.lemma_id, { q: input.value.trim(), form: s.form || "", mt: s.match_type });
        }
      } else if (event.key === "Escape") {
        close();
      }
    });

    input.addEventListener("blur", () => setTimeout(close, 120));
    input.addEventListener("focus", () => {
      if (input.value.trim().length >= 2) fetchSuggestions(input.value.trim());
    });

    const form = el(
      "form.search",
      {
        attrs: { role: "search", autocomplete: "off" },
        onSubmit: (event) => {
          event.preventDefault();
          const value = input.value.trim();
          if (!value) {
            input.focus();
            return;
          }
          close();
          if (opts.onSubmit) opts.onSubmit(mode, value);
          else WH.router.go(mode, {}, { q: value });
        },
      },
      tabs,
      row,
      hints
    );

    form.input = input;
    form.focus = () => {
      input.focus();
      input.select();
    };
    return form;
  };

  /* navigation helpers used by several views */
  const Go = {
    entry(lemmaId, query) {
      WH.router.go("entry", { id: lemmaId }, query);
    },
    lookup(q) {
      WH.router.go("lookup", {}, { q });
    },
    semantic(q) {
      WH.router.go("semantic", {}, { q });
    },
  };
  ui.Go = Go;

  /* ---------------------------------------------------------------- tiles -- */

  ui.tegel = function (item) {
    const word = item.lemma;
    return el(
      "a.tegel",
      {
        href: WH.router.build("entry", { id: item.lemma_id }),
        attrs: { "aria-label": word + " — " + (item.gloss || "") },
      },
      el("span.tegel__lvl", null, item.level ? "L" + item.level : ""),
      el("span.tegel__word", null, WH.withDigraph(word)),
      el("span.tegel__gloss", null, item.gloss || "—")
    );
  };

  /* -------------------------------------------------------------- notices -- */

  ui.notice = function (text, kind) {
    const cls = kind === "warn" ? ".notice.notice--warn" : kind === "bad" ? ".notice.notice--bad" : ".notice";
    return el(
      "div" + cls,
      null,
      icon(kind === "bad" ? "alert" : "info", { size: 15 }),
      el("div", null, text)
    );
  };

  ui.state = function ({ code, title, text, actions = [], iconName = "windmill" }) {
    return el(
      "div.state",
      null,
      el(
        "div.state__plate",
        null,
        icon(iconName, { size: 40, class: "state__icon" })
      ),
      code ? el("p.state__code", null, code) : null,
      el("h2", null, title),
      el("p", null, text),
      actions.length ? el("div.state__actions", null, actions) : null
    );
  };

  /** an error rendered from an ApiError, with context-aware actions */
  ui.errorPanel = function (err, context = {}) {
    const info = WH.describeError(err);
    const actions = [];
    if (info.kind === "rate") {
      const seconds = info.retryAfter || 30;
      const label = el("span", null, "重试");
      const button = el(
        "button.btn.btn--primary",
        { attrs: { type: "button", disabled: true } },
        el("span.countdown", null, seconds + "s"),
        label
      );
      let left = seconds;
      const tick = setInterval(() => {
        left -= 1;
        if (left <= 0) {
          clearInterval(tick);
          button.removeAttribute("disabled");
          const cd = button.querySelector(".countdown");
          if (cd) cd.remove();
          label.textContent = "重试";
        } else {
          const cd = button.querySelector(".countdown");
          if (cd) cd.textContent = left + "s";
        }
      }, 1000);
      button.addEventListener("click", () => {
        if (button.hasAttribute("disabled")) return;
        if (context.retry) context.retry();
      });
      actions.push(button);
      actions.push(
        el(
          "button.btn.btn--ghost",
          {
            attrs: { type: "button" },
            onClick: () => WH.router.go("home"),
          },
          "回到查词"
        )
      );
    } else {
      if (context.retry) {
        actions.push(
          el(
            "button.btn.btn--primary",
            { attrs: { type: "button" }, onClick: () => context.retry() },
            "重试"
          )
        );
      }
      if (info.semanticDisabled) {
        actions.push(
          el(
            "button.btn.btn--ghost",
            {
              attrs: { type: "button" },
              onClick: () => WH.router.go("home", {}, { q: context.query || "" }),
            },
            "改用普通查词"
          )
        );
      } else {
        actions.push(
          el(
            "button.btn.btn--ghost",
            { attrs: { type: "button" }, onClick: () => WH.router.go("home") },
            "回到查词"
          )
        );
      }
    }
    return ui.state({
      code: info.code,
      title: info.title,
      text: info.text,
      actions,
      iconName: info.kind === "rate" ? "clock" : "windmill",
    });
  };

  ui.skeletonEntry = function () {
    return el(
      "div.wrap",
      { style: "padding-top:40px" },
      el("div.skeleton.sk-line.w-40", null),
      el("div.skeleton.sk-head", null),
      el("div.skeleton.sk-line.w-60", { style: "height:16px;margin-bottom:6px" }),
      el("div.skeleton.sk-line.w-40", { style: "height:16px;margin-bottom:36px" }),
      el(
        "div",
        { style: "display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:48px" },
        el(
          "div",
          null,
          [0, 1, 2].map(() =>
            el(
              "div",
              { style: "margin-bottom:28px" },
              el("div.skeleton.sk-line.w-40", { style: "height:24px" }),
              el("div.skeleton.sk-line.w-80"),
              el("div.skeleton.sk-line.w-60")
            )
          )
        ),
        el("div", null, el("div.skeleton.sk-card", null), el("div.skeleton.sk-card", { style: "margin-top:16px" }))
      )
    );
  };

  ui.skeletonResults = function () {
    return el(
      "div.wrap",
      { style: "padding-top:40px" },
      el("div.skeleton.sk-line.w-40", null),
      el(
        "div",
        { style: "display:grid;gap:22px;margin-top:24px" },
        [0, 1, 2, 3, 4].map(() =>
          el(
            "div",
            null,
            el("div.skeleton.sk-line", { style: "height:26px;width:32%" }),
            el("div.skeleton.sk-line.w-60", { style: "height:14px" }),
            el("div.skeleton.sk-line.w-40", { style: "height:14px" })
          )
        )
      )
    );
  };

  /* ------------------------------------------------------------- inspector -- */

  ui.inspector = function () {
    const panel = el("div.inspector", null);
    const toggle = el(
      "button.inspector__toggle",
      {
        attrs: { type: "button", "aria-expanded": "false" },
        onClick: () => {
          const open = panel.classList.toggle("is-open");
          toggle.setAttribute("aria-expanded", String(open));
        },
      },
      icon("layers", { size: 14 }),
      "状态预览"
    );

    const scenarios = WH.api.scenarios ? WH.api.scenarios() : [];
    const groups = [
      { label: "查词 / 联想", test: (s) => s.path === "/lookup" || s.path === "/suggest" },
      { label: "词条 / 分页 / 例句", test: (s) => s.path.startsWith("/entries") || s.path.startsWith("/senses") },
      { label: "按意思找词", test: (s) => s.path === "/semantic-search" },
      { label: "错误与回退", test: (s) => s.status >= 400 },
    ];

    const listNode = el("div.inspector__list");
    const seen = new Set();
    for (const group of groups) {
      const items = scenarios.filter((s) => !seen.has(s.id) && group.test(s));
      if (!items.length) continue;
      items.forEach((s) => seen.add(s.id));
      listNode.appendChild(el("div.inspector__group", null, group.label));
      for (const s of items) {
        listNode.appendChild(
          el(
            "button.inspector__item",
            {
              attrs: { type: "button", title: s.title || s.id },
              onClick: () => {
                WH.app.playScenario(s);
                panel.classList.remove("is-open");
                toggle.setAttribute("aria-expanded", "false");
              },
            },
            el("code", null, s.id.slice(0, 22)),
            el("span", null, (s.title || "").replace(/^真实改写校准：/, "校准：").slice(0, 26)),
            el(
              "span.inspector__status",
              { style: s.status >= 400 ? "color:var(--rood);border-color:currentColor" : "" },
              String(s.status)
            )
          )
        );
      }
    }

    const panelInner = el(
      "div.inspector__panel",
      { attrs: { role: "dialog", "aria-label": "录制场景预览" } },
      el(
        "div.inspector__head",
        null,
        el("span", null, "回放 " + scenarios.length + " 个录制响应"),
        el(
          "button.link-btn",
          {
            attrs: { type: "button" },
            onClick: () => {
              WH.api.forceScenario(null);
              toast("已取消强制场景");
            },
          },
          "清除强制"
        )
      ),
      listNode,
      el(
        "div.inspector__head",
        { style: "border-top:1px solid var(--rule);border-bottom:none" },
        el("span", null, WH.api.mode === "demo" ? "当前：离线回放" : "当前：" + WH.api.base)
      )
    );

    panel.appendChild(panelInner);
    panel.appendChild(toggle);
    return panel;
  };

  ui.guide = function () {
    const cards = [
      {
        title: "IJ 是一个字母",
        nl: "[ɛi] · 排序等同 y",
        text: "词首大写时两个字母一起大写。",
        ex: "IJsselmeer · ijsbeer",
      },
      {
        title: "de / het",
        nl: "通性 / 中性",
        text: "约四分之三的名词用 de。接口没收录就留空。",
        ex: "de fiets · het huis",
      },
      {
        title: "复合词",
        nl: "samenstellingen",
        text: "名词直接拼成一个词，中间可带 -s- / -en-。",
        ex: "huisdeur · ziekenhuis",
      },
      {
        title: "可分动词",
        nl: "scheidbare werkwoorden",
        text: "前缀跑到句尾；分词把 ge- 夹在中间。",
        ex: "afzetten → zet af → afgezet",
      },
      {
        title: "指小词 -je",
        nl: "verkleinwoorden",
        text: "-je / -tje / -pje：小、亲昵或轻描淡写。",
        ex: "huis → huisje · kopje",
      },
      {
        title: "拼写会变",
        nl: "spelling",
        text: "长元音补字母；s/z、f/v 在词尾交替。",
        ex: "huis → huizen · reis",
      },
    ];

    return el(
      "dialog.sheet",
      { attrs: { "aria-label": "荷兰语语言指南" } },
      el(
        "div.sheet__head",
        null,
        el("h2.sheet__title", null, "Taalwijzer · 六条"),
        el(
          "button.icon-btn",
          {
            attrs: { type: "button", "aria-label": "关闭" },
            onClick: (event) => event.target.closest("dialog").close(),
          },
          icon("close", { size: 18 })
        )
      ),
      el(
        "div.sheet__body",
        null,
        el(
          "div.guide-grid",
          null,
          cards.map((c) =>
            el(
              "div.guide-card",
              null,
              el("h3", null, c.title),
              el("p.nl", null, c.nl),
              el("p", null, c.text),
              el("p.example", null, c.ex)
            )
          )
        )
      )
    );
  };

  ui.openGuide = function () {
    let dialog = document.querySelector("dialog.sheet");
    if (!dialog) {
      dialog = ui.guide();
      document.body.appendChild(dialog);
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close();
      });
    }
    dialog.showModal();
  };
})();
