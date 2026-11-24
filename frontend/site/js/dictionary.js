/* User-facing dictionary. Model calls happen only on explicit form submission. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const input = $("query"),
    results = $("results"),
    status = $("status");
  const base = (new URLSearchParams(location.search).get("api") || "").replace(
    /\/+$/,
    "",
  );
  const modes = {
    lookup: {
      label: "输入荷兰语词或词形",
      placeholder: "输入荷兰语词或词形，如 huizen",
      hint: "输入时联想，回车查询。",
      max: 128,
    },
    semantic: {
      label: "描述你想找的意思",
      placeholder: "描述一个意思，如「可以借书的地方」",
      hint: "用中文、英文或荷兰语描述，回车找词。",
      max: 512,
    },
  };
  let mode = "lookup",
    main = null,
    suggestController = null,
    suggestTimer = null,
    suggestionEpoch = 0,
    options = [],
    selected = -1,
    composing = false,
    lastSuggest = 0,
    cooldown = 0,
    cooldownTimer = null,
    current = null;
  const suggestionCache = new Map(),
    views = new Map();
  function el(tag, text, cls) {
    const n = document.createElement(tag);
    if (text !== undefined && text !== null) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  }
  function text(text, error = false) {
    status.replaceChildren();
    status.textContent = text;
    status.hidden = !text;
    status.classList.toggle("error", error);
  }
  function arrow() {
    const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("fill", "none");
    s.setAttribute("aria-hidden", "true");
    const p = document.createElementNS(s.namespaceURI, "path");
    p.setAttribute("d", "M5 12h14m-6-6 6 6-6 6");
    s.append(p);
    return s;
  }
  function boundedCache(cache, key, value, limit = 24) {
    cache.delete(key);
    cache.set(key, value);
    if (cache.size > limit) cache.delete(cache.keys().next().value);
  }
  function closeSuggestions() {
    clearTimeout(suggestTimer);
    suggestionEpoch++;
    if (suggestController) suggestController.abort();
    suggestController = null;
    options = [];
    selected = -1;
    $("suggestions").hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }
  function stop() {
    if (main) main.abort();
    main = null;
    results.removeAttribute("aria-busy");
    updateButton();
  }
  function updateButton() {
    const wait = Math.ceil((cooldown - Date.now()) / 1000);
    $("search-button").disabled = !!main || wait > 0;
    $("search-button").querySelector("span").textContent =
      wait > 0 ? `${wait} 秒` : "查询";
    $("search-button").setAttribute(
      "aria-label",
      wait > 0 ? `请等待 ${wait} 秒后查询` : "查询",
    );
    if (wait <= 0 && cooldownTimer) {
      clearInterval(cooldownTimer);
      cooldownTimer = null;
    }
  }
  function setCooldown(value) {
    text("查询有些频繁，请稍等片刻再试。", true);
    const seconds = Number(value),
      until =
        value && /^\d+$/.test(value)
          ? Date.now() + seconds * 1000
          : Date.parse(value || "");
    cooldown = Math.max(
      cooldown,
      Number.isFinite(until) && until > Date.now() ? until : Date.now() + 10000,
    );
    closeSuggestions();
    if (!cooldownTimer) cooldownTimer = setInterval(updateButton, 1000);
    updateButton();
  }
  function changeMode(value) {
    mode = value === "semantic" ? "semantic" : "lookup";
    closeSuggestions();
    const spec = modes[mode];
    input.placeholder = spec.placeholder;
    input.maxLength = spec.max;
    input.setAttribute(
      "aria-autocomplete",
      mode === "lookup" ? "list" : "none",
    );
    $("query-label").textContent = spec.label;
    $("search-hint").textContent = spec.hint;
    document
      .querySelectorAll("[data-mode]")
      .forEach((b) =>
        b.setAttribute("aria-pressed", String(b.dataset.mode === mode)),
      );
  }
  async function request(path, { signal, body } = {}) {
    if (Date.now() < cooldown)
      throw new Error("查询有些频繁，请稍等片刻再试。");
    const c = new AbortController(),
      forward = () => c.abort();
    if (signal?.aborted) c.abort();
    else signal?.addEventListener("abort", forward, { once: true });
    const timer = setTimeout(() => c.abort("timeout"), 35000);
    try {
      const r = await fetch(base + path, {
        signal: c.signal,
        method: body ? "POST" : "GET",
        headers: body ? { "Content-Type": "application/json" } : {},
        body: body ? JSON.stringify(body) : undefined,
        cache: "no-store",
      });
      if (r.status === 429) {
        setCooldown(r.headers.get("Retry-After"));
        throw new Error("查询有些频繁，请稍等片刻再试。");
      }
      if (!r.ok)
        throw new Error(
          r.status === 404
            ? "暂时没有找到这个词条。"
            : r.status === 422
              ? "输入内容过长或格式不正确，请调整后再试。"
              : "暂时无法完成查询，请稍后再试。",
        );
      return await r.json();
    } catch (e) {
      if (e.name === "AbortError" && !signal?.aborted)
        throw new Error("查询时间较长，请稍后再试。");
      if (e instanceof SyntaxError)
        throw new Error("暂时无法读取查询结果，请稍后再试。");
      if (e instanceof TypeError)
        throw new Error("连接暂时中断，请检查网络后重试。");
      throw e;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", forward);
    }
  }
  function hashFor(kind, q, id) {
    const p = new URLSearchParams({ q });
    if (kind === "entry") {
      p.set("mode", mode);
      return "#/woord/" + id + "?" + p;
    }
    return "#/" + (kind === "semantic" ? "betekenis" : "zoeken") + "?" + p;
  }
  function save(view, hash, replace = false) {
    current = view;
    boundedCache(views, hash, view, 12);
    if (location.hash !== hash)
      history[replace ? "replaceState" : "pushState"](null, "", hash);
    render(view);
  }
  function reveal() {
    document.body.classList.add("has-results");
    results.hidden = false;
  }
  async function action(task) {
    stop();
    closeSuggestions();
    const c = new AbortController();
    main = c;
    updateButton();
    results.setAttribute("aria-busy", "true");
    text("正在查找…");
    try {
      await task(c.signal);
      if (main === c) text("");
    } catch (e) {
      if (!c.signal.aborted && main === c) text(e.message, true);
    } finally {
      if (main === c) {
        main = null;
        results.removeAttribute("aria-busy");
        updateButton();
      }
    }
  }
  async function openEntry(id, q, kind = mode, replace = false, back = null) {
    changeMode(kind);
    input.value = q || "";
    $("clear").hidden = !input.value;
    const hash = hashFor("entry", q || "", id);
    await action(async (signal) => {
      const data = await request(
        `/entries/${id}?sense_limit=10&example_limit=3`,
        { signal },
      );
      if (signal.aborted) return;
      const view = {
        kind: "entry",
        data,
        q: q || data.lemma,
        mode: kind,
        back,
      };
      if (!q) {
        input.value = data.lemma;
        $("clear").hidden = !input.value;
      }
      save(view, hash, replace);
      window.scrollTo(0, 0);
      document.title = data.lemma + " · Woordhuis";
    });
  }
  async function search() {
    const q = input.value.trim();
    if (!q) {
      text(mode === "lookup" ? "先输入一个荷兰语词。" : "先描述你想找的意思。");
      input.focus();
      return;
    }
    const kind = mode;
    if (q.length > modes[kind].max) {
      text("输入内容过长，请缩短后再试。", true);
      return;
    }
    const hash = hashFor(kind, q);
    const previousHash = location.hash;
    await action(async (signal) => {
      const data =
        kind === "lookup"
          ? await request("/lookup?" + new URLSearchParams({ q, limit: "5" }), {
              signal,
            })
          : await request("/semantic-search", {
              signal,
              body: { query: q, limit: 10, include_related: true },
            });
      if (signal.aborted) return;
      if (kind === "lookup" && data.best_match) {
        const entry = await request(
          `/entries/${data.best_match.lemma_id}?sense_limit=10&example_limit=3`,
          { signal },
        );
        if (signal.aborted) return;
        save(
          { kind: "entry", data: entry, q, mode: kind, back: null },
          hashFor("entry", q, entry.lemma_id),
        );
        document.title = entry.lemma + " · Woordhuis";
      } else {
        save(
          {
            kind: kind === "lookup" ? "empty" : "semantic",
            data,
            q,
            mode: kind,
            back: previousHash,
          },
          hash,
        );
        document.title = q + " · Woordhuis";
      }
    });
  }
  function drawSuggestions(items) {
    items = items.slice(0, 6);
    options = items;
    selected = -1;
    const list = $("suggestions");
    list.replaceChildren();
    items.forEach((item, i) => {
      const li = el("li");
      li.id = "suggestion-" + i;
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", "false");
      li.append(el("span", item.lemma));
      if (item.form && item.form !== item.lemma)
        li.append(el("span", item.form, "suggest-form"));
      li.addEventListener("pointerdown", (e) => e.preventDefault());
      li.addEventListener("click", () =>
        openEntry(item.lemma_id, item.form || item.lemma, "lookup"),
      );
      list.append(li);
    });
    list.hidden = !items.length;
    input.setAttribute("aria-expanded", String(!!items.length));
    input.removeAttribute("aria-activedescendant");
  }
  function scheduleSuggestions() {
    closeSuggestions();
    const q = input.value.trim();
    if (
      mode !== "lookup" ||
      composing ||
      q.length < 1 ||
      q.length > 128 ||
      Date.now() < cooldown
    )
      return;
    const epoch = suggestionEpoch;
    if (suggestionCache.has(q)) {
      drawSuggestions(suggestionCache.get(q));
      return;
    }
    suggestTimer = setTimeout(
      async () => {
        const c = new AbortController();
        suggestController = c;
        lastSuggest = Date.now();
        try {
          const data = await request(
            "/suggest?" + new URLSearchParams({ q, limit: "6" }),
            { signal: c.signal },
          );
          if (
            epoch !== suggestionEpoch ||
            mode !== "lookup" ||
            input.value.trim() !== q ||
            document.activeElement !== input
          )
            return;
          boundedCache(suggestionCache, q, data.suggestions || [], 32);
          drawSuggestions(data.suggestions || []);
        } catch (e) {
          if (!c.signal.aborted && epoch === suggestionEpoch)
            text(e.message, true);
        } finally {
          if (suggestController === c) suggestController = null;
        }
      },
      Math.max(320, 1100 - (Date.now() - lastSuggest)),
    );
  }
  function translation(s, lang) {
    const t = (s.translations || []).find((t) => t.lang === lang);
    return t?.explanation || t?.gloss || s["translation_" + lang] || "";
  }
  function labeled(tag, label, value, className, lang) {
    const row = el(tag, null, className);
    const content = el("span", value, "content-value");
    if (lang) content.lang = lang;
    row.append(el("span", label, "content-label"), content);
    return row;
  }
  function examples(items, target) {
    for (const item of items || []) {
      const block = el("blockquote", null, "example");
      block.append(labeled("p", "荷文例句", item.ex_nl, null, "nl"));
      for (const t of item.translations || [])
        if (t.lang === "zh" || t.lang === "en")
          block.append(
            labeled(
              "p",
              t.lang === "zh" ? "中文例句翻译" : "英文例句翻译",
              t.translation,
              "example-translation",
              t.lang === "zh" ? "zh-CN" : "en",
            ),
          );
      target.append(block);
    }
  }
  function moreButton(action, label, group, id) {
    const b = el("button", label, "more-button");
    b.type = "button";
    b.dataset.action = action;
    if (group) b.dataset.group = group;
    if (id) b.dataset.sense = id;
    return b;
  }
  function levelBadge(level) {
    const labels = {1: "一级词汇", 2: "二级词汇", 3: "三级词汇", 4: "四级词汇"};
    return Number.isInteger(level) && labels[level] ? el("span", labels[level], "level-badge") : null;
  }
  function wordLink(item, kind, q) {
    const a = el("a", null, "result-link");
    a.href =
      "#/woord/" + item.lemma_id + "?" + new URLSearchParams({ q, mode: kind });
    a.dataset.entry = item.lemma_id;
    a.dataset.word = item.lemma;
    a.dataset.mode = kind;
    const copy = el("div", null, "result-copy");
    const title = el("div", null, "word-title");
    title.append(el("h2", item.lemma));
    const badge = levelBadge(item.level);
    if (badge) title.append(badge);
    copy.append(title);
    const sense = item.matched_sense || {};
    if (sense.translation_zh)
      copy.append(
        labeled("p", "中文释义", sense.translation_zh, null, "zh-CN"),
      );
    if (sense.definition_nl)
      copy.append(labeled("p", "荷文释义", sense.definition_nl, null, "nl"));
    if (sense.translation_en)
      copy.append(
        labeled("p", "英文释义", sense.translation_en, "english", "en"),
      );
    a.append(copy, arrow());
    return a;
  }
  function extra(title) {
    const d = el("details", null, "entry-extra");
    d.append(el("summary", title));
    return d;
  }
  function renderEntry(view) {
    const d = view.data;
    const label = el("div", null, "result-label");
    label.append(
      el(
        "p",
        view.q && view.q !== d.lemma ? `「${view.q}」的词条` : "词条详情",
      ),
    );
    if (view.back && view.back.startsWith("#/betekenis")) {
      const a = el("a", "← 返回找词结果", "back-link");
      a.href = view.back;
      label.append(a);
    }
    results.append(label);
    const card = el("article", null, "word-entry");
    const head = el("header", null, "entry-heading");
    const title = el("div", null, "word-title");
    title.append(el("h2", d.display_lemma || d.lemma));
    const badge = levelBadge(d.level);
    if (badge) title.append(badge);
    head.append(title);
    const meta = el("div", null, "entry-meta");
    const pos = [
      ...new Set(
        (d.parts_of_speech || []).map((p) => p.label_zh).filter(Boolean),
      ),
    ];
    if (pos.length) meta.append(el("span", "词性：" + pos.join(" · ")));
    const articles = [
      ...new Set(
        (d.parts_of_speech || []).map((p) => p.article).filter(Boolean),
      ),
    ];
    if (articles.length)
      meta.append(el("span", "冠词：" + articles.join(" / ")));
    if (d.cefr_level) meta.append(el("span", d.cefr_level));
    head.append(meta);
    card.append(head);
    const sh = el("h3", "释义", "section-heading");
    if (d.senses?.total != null)
      sh.append(el("span", `${d.senses.total} 个义项`));
    card.append(sh);
    if (!d.senses?.items?.length)
      card.append(el("p", "这个词的释义正在整理。", "usage"));
    for (const [i, s] of (d.senses?.items || []).entries()) {
      const row = el("section", null, "sense");
      row.append(el("span", String(i + 1).padStart(2, "0"), "sense-number"));
      const body = el("div");
      const zh = translation(s, "zh"),
        en = translation(s, "en");
      if (zh) body.append(labeled("h3", "中文释义", zh, null, "zh-CN"));
      if (s.definition_nl)
        body.append(
          labeled(
            zh ? "p" : "h3",
            "荷文释义",
            s.definition_nl,
            "definition",
            "nl",
          ),
        );
      if (!zh && !s.definition_nl) body.append(el("h3", "释义待补充"));
      if (en) body.append(labeled("p", "英文释义", en, "english", "en"));
      if (s.usage_note)
        body.append(labeled("p", "用法说明", s.usage_note, "usage"));
      examples(s.examples?.items, body);
      if (s.examples?.has_more)
        body.append(moreButton("examples", "更多例句", null, s.sense_id));
      row.append(body);
      card.append(row);
    }
    if (d.senses?.has_more)
      card.append(moreButton("page", "更多释义", "senses"));
    if (d.forms?.items?.length) {
      const box = extra("词形");
      const list = el("div", null, "form-list");
      for (const f of d.forms.items) {
        const token = el("span", f.form, "form-token");
        if (f.display_label_zh) token.append(el("small", f.display_label_zh));
        list.append(token);
      }
      box.append(list);
      if (d.forms.has_more) box.append(moreButton("page", "更多词形", "forms"));
      card.append(box);
    }
    if (d.expressions?.items?.length) {
      const box = extra("常用表达");
      for (const x of d.expressions.items) {
        const block = el("div", null, "expression");
        block.append(labeled("h3", "荷文表达", x.expression_nl, null, "nl"));
        if (x.explanation_zh || x.gloss_zh)
          block.append(
            labeled(
              "p",
              "中文释义",
              x.explanation_zh || x.gloss_zh,
              "definition",
              "zh-CN",
            ),
          );
        if (x.explanation_en || x.gloss_en)
          block.append(
            labeled(
              "p",
              "英文释义",
              x.explanation_en || x.gloss_en,
              "english",
              "en",
            ),
          );
        if (x.example_nl)
          examples(
            [
              {
                ex_nl: x.example_nl,
                translations: x.example_zh
                  ? [{ lang: "zh", translation: x.example_zh }]
                  : [],
              },
            ],
            block,
          );
        box.append(block);
      }
      if (d.expressions.has_more)
        box.append(moreButton("page", "更多表达", "expressions"));
      card.append(box);
    }
    if (d.corpus_examples?.items?.length) {
      const box = extra("语料例句");
      box.append(el("p", "来自真实语料，未按义项区分。", "usage"));
      examples(d.corpus_examples.items, box);
      if (d.corpus_examples.has_more)
        box.append(moreButton("page", "更多语料例句", "corpus_examples"));
      card.append(box);
    }
    if (d.sources?.length) {
      const box = extra("来源与许可");
      const content = el("div", null, "sources");
      for (const s of d.sources) {
        const p = el("p");
        if (/^https?:\/\//i.test(s.url || "")) {
          const a = el("a", s.name);
          a.href = s.url;
          a.rel = "noopener noreferrer";
          a.target = "_blank";
          p.append(a);
        } else p.append(el("span", s.name));
        if (s.license) {
          p.append(el("span", " · "));
          if (/^https?:\/\//i.test(s.license_url || "")) {
            const license = el("a", s.license);
            license.href = s.license_url;
            license.target = "_blank";
            license.rel = "noopener noreferrer";
            p.append(license);
          } else p.append(el("span", s.license));
        }
        if (s.attribution && !s.attribution.includes("/Users/"))
          p.append(el("span", " — " + s.attribution));
        content.append(p);
      }
      box.append(content);
      card.append(box);
    }
    results.append(card);
  }
  function render(view) {
    $("announcement").textContent =
      view.kind === "entry"
        ? "已显示 " + view.data.lemma + " 的词条详情。"
        : "已显示查询结果。";
    current = view;
    document.title =
      (view.kind === "entry" ? view.data.lemma : view.q) + " · Woordhuis";
    reveal();
    results.replaceChildren();
    if (view.kind === "entry") {
      renderEntry(view);
      return;
    }
    if (view.kind === "semantic") {
      const label = el("div", null, "result-label");
      label.append(el("p", `与「${view.q}」相关的词`));
      results.append(label);
      const list = el("ul", null, "result-list");
      for (const r of view.data.results || []) {
        const li = el("li", null, "result-card");
        li.append(wordLink(r, "semantic", view.q));
        list.append(li);
      }
      results.append(list);
      if (!view.data.results?.length)
        results.append(
          el("p", "暂时没有找到合适的词，试着换一种描述。", "empty-state"),
        );
      if (view.data.related_results?.length) {
        const box = extra("相关词");
        for (const r of view.data.related_results)
          box.append(wordLink(r, "semantic", view.q));
        results.append(box);
      }
      return;
    }
    const empty = el("div", null, "empty-state");
    empty.append(
      el("h2", "没有找到这个词"),
      el("p", "检查一下拼写，或切换「按意思找词」描述它。"),
    );
    if (view.data.did_you_mean?.length) {
      empty.append(el("p", "你是否想查："));
      const list = el("div", null, "candidate-list");
      for (const item of view.data.did_you_mean) {
        const a = el("a", item.lemma);
        a.href =
          "#/woord/" +
          item.lemma_id +
          "?" +
          new URLSearchParams({ q: item.lemma, mode: "lookup" });
        a.dataset.entry = item.lemma_id;
        a.dataset.word = item.lemma;
        a.dataset.mode = "lookup";
        list.append(a);
      }
      empty.append(list);
    }
    results.append(empty);
  }
  async function page(button) {
    if (!current || current.kind !== "entry" || button.disabled) return;
    const view = current;
    const group = button.dataset.group;
    const sense =
      button.dataset.sense &&
      (view.data.senses.items || []).find(
        (s) => String(s.sense_id) === button.dataset.sense,
      );
    const old = sense ? sense.examples : view.data[group];
    if (!old?.has_more) return;
    const prefix = {
      senses: "sense",
      forms: "form",
      expressions: "expression",
      corpus_examples: "example",
    }[group];
    const url = sense
      ? `/senses/${sense.sense_id}/examples?offset=${old.next_offset}&limit=10`
      : `/entries/${view.data.lemma_id}?${prefix}_offset=${old.next_offset}&${prefix}_limit=${group === "forms" ? 50 : 10}`;
    button.disabled = true;
    text("正在加载…");
    const c = new AbortController();
    stop();
    main = c;
    updateButton();
    try {
      const data = await request(url, { signal: c.signal });
      if (c.signal.aborted || current !== view) return;
      const next = sense ? data.examples : data[group];
      const merged = { ...next, items: [...old.items, ...next.items] };
      if (sense) sense.examples = merged;
      else view.data[group] = merged;
      const opened = [...results.querySelectorAll("details[open]")].map(
        (n) => n.querySelector("summary")?.textContent,
      );
      const y = window.scrollY;
      render(view);
      results.querySelectorAll("details").forEach((n) => {
        if (opened.includes(n.querySelector("summary")?.textContent))
          n.open = true;
      });
      window.scrollTo(0, y);
      text("");
    } catch (e) {
      if (!c.signal.aborted) text(e.message, true);
    } finally {
      if (main === c) {
        main = null;
        updateButton();
      }
      button.disabled = false;
    }
  }
  function route() {
    stop();
    closeSuggestions();
    text("");
    const hash = location.hash || "#/";
    if (views.has(hash)) {
      const v = views.get(hash);
      changeMode(v.mode);
      input.value = v.q;
      $("clear").hidden = !input.value;
      render(v);
      return;
    }
    const raw = hash.slice(1),
      mark = raw.indexOf("?"),
      path = mark < 0 ? raw : raw.slice(0, mark),
      p = new URLSearchParams(mark < 0 ? "" : raw.slice(mark + 1));
    const id = /^\/woord\/(\d+)$/.exec(path);
    changeMode(
      path === "/betekenis" || p.get("mode") === "semantic"
        ? "semantic"
        : "lookup",
    );
    input.value = p.get("q") || "";
    $("clear").hidden = !input.value;
    results.hidden = true;
    results.replaceChildren();
    current = null;
    document.body.classList.remove("has-results");
    document.title = "Woordhuis · 荷兰语词典";
    if (id) openEntry(id[1], input.value, mode, true);
    else if (path === "/zoeken" && input.value) search();
  }
  $("search-form").addEventListener("submit", (e) => {
    e.preventDefault();
    if (composing) return;
    if (selected >= 0 && options[selected]) {
      const item = options[selected];
      openEntry(item.lemma_id, item.form || item.lemma, "lookup");
    } else search();
  });
  document.querySelectorAll("[data-mode]").forEach((b) =>
    b.addEventListener("click", () => {
      if (mode === b.dataset.mode) return;
      stop();
      changeMode(b.dataset.mode);
      const h =
        "#/" +
        (mode === "semantic" ? "betekenis" : "zoeken") +
        (input.value ? "?" + new URLSearchParams({ q: input.value }) : "");
      history.pushState(null, "", h);
      results.hidden = true;
      current = null;
      document.body.classList.remove("has-results");
      document.title = "Woordhuis · 荷兰语词典";
      text("");
      input.focus();
    }),
  );
  input.addEventListener("input", () => {
    stop();
    text(
      Date.now() < cooldown ? "查询有些频繁，请稍等片刻再试。" : "",
      Date.now() < cooldown,
    );
    $("clear").hidden = !input.value;
    scheduleSuggestions();
  });
  input.addEventListener("compositionstart", () => {
    composing = true;
    closeSuggestions();
  });
  input.addEventListener("compositionend", () => {
    composing = false;
    scheduleSuggestions();
  });
  input.addEventListener("focus", () => {
    if (mode === "lookup") scheduleSuggestions();
  });
  input.addEventListener("keydown", (e) => {
    if (composing || e.isComposing) return;
    if (e.key === "Escape") {
      closeSuggestions();
      return;
    }
    if (e.key === "Tab") {
      closeSuggestions();
      return;
    }
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && options.length) {
      e.preventDefault();
      selected =
        e.key === "ArrowDown"
          ? (selected + 1) % options.length
          : selected < 0
            ? options.length - 1
            : (selected - 1 + options.length) % options.length;
      [...$("suggestions").children].forEach((n, i) =>
        n.setAttribute("aria-selected", String(i === selected)),
      );
      input.setAttribute("aria-activedescendant", "suggestion-" + selected);
      $("suggestions").children[selected].scrollIntoView({ block: "nearest" });
    }
  });
  $("clear").addEventListener("click", () => {
    stop();
    closeSuggestions();
    input.value = "";
    $("clear").hidden = true;
    text("");
    input.focus();
  });
  document.addEventListener("pointerdown", (e) => {
    if (!$("search-wrap").contains(e.target)) closeSuggestions();
  });
  input.addEventListener("blur", () =>
    setTimeout(() => {
      if (document.activeElement !== input) closeSuggestions();
    }, 0),
  );
  results.addEventListener("click", (e) => {
    const link = e.target.closest("a[data-entry]");
    if (link && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) {
      e.preventDefault();
      const back = current?.kind === "semantic" ? location.hash : null;
      openEntry(
        link.dataset.entry,
        current?.kind === "semantic" ? current.q : link.dataset.word,
        link.dataset.mode,
        false,
        back,
      );
      return;
    }
    const button = e.target.closest("button[data-action]");
    if (button) page(button);
  });
  document.querySelector(".skip-link").addEventListener("click", (e) => {
    e.preventDefault();
    input.focus();
  });
  window.addEventListener("hashchange", route);
  route();
})();
