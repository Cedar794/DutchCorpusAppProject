/* One explicit action = one API request. Render the response without enrichment. */
(function () {
  "use strict";

  const ENDPOINTS = {
    lookup: { method: "GET", path: "/lookup", route: "/zoeken", label: "查询词 q", placeholder: "输入荷兰语词或词形，如 huizen", params: { limit: [5, "1–5"] } },
    semantic: { method: "POST", path: "/semantic-search", route: "/betekenis", label: "描述 query", placeholder: "用中文、英文或荷兰语描述要找的意思", params: { limit: [10, "1–50"], include_related: [true, "包含关联词"] } },
    suggest: { method: "GET", path: "/suggest", route: "/suggest", label: "前缀 q", placeholder: "输入前缀，如 hui", params: { limit: [10, "1–20"] } },
    entry: { method: "GET", path: "/entries/{id}", route: "/woord", label: "词头 ID · lemma_id", placeholder: "输入词头 ID，如 138", params: {
      sense_offset: [0, "0–10000"], sense_limit: [20, "1–50"],
      form_offset: [0, "0–100000"], form_limit: [50, "1–100"],
      example_offset: [0, "0–10000"], example_limit: [5, "1–20"],
      expression_offset: [0, "0–10000"], expression_limit: [20, "1–50"],
    } },
    examples: { method: "GET", path: "/senses/{id}/examples", route: "/examples", label: "义项 ID · sense_id", placeholder: "输入义项 ID，如 12960", params: { offset: [0, "0–10000"], limit: [10, "1–20"] } },
  };

  const LABELS = {
    query: "查询", mode: "模式", best_match: "最佳匹配", did_you_mean: "纠错候选", suggestions: "联想候选",
    results: "检索结果", related_results: "关联词", query_rewrite: "查询改写", language: "语言",
    lemma_id: "词头 ID", lemma: "词头", display_lemma: "展示词头", entry_url: "词条接口", level: "项目分级",
    cefr_level: "CEFR 等级", word_family: "词族", family_head_lemma_id: "词族中心 ID", frequency: "语料频次", is_academic: "学术词",
    form_id: "词形 ID", form: "词形", match_type: "匹配类型", score: "排序分", confidence: "置信度（启发式）",
    matched_sense: "匹配义项", matched_reason: "排序构成", semantic_score: "向量相似度", frequency_boost: "词频加权", level_boost: "分级加权",
    status: "状态", model: "模型", prompt_version: "提示词版本", detail: "错误详情", loc: "参数位置", msg: "错误说明", type: "类型", input: "输入", ctx: "上下文",
    parts_of_speech: "词性", lemma_pos_entry_id: "词性记录 ID", pos: "词性标签", app_pos: "应用词性", label_zh: "中文名称", label_en: "英文名称", label_nl: "荷文名称",
    gender: "性", article: "冠词", is_primary: "主要项", needs_review: "待复核标记", review_status: "审核状态",
    senses: "义项", sense_id: "义项 ID", sense_no: "源义项编号", definition_nl: "荷文释义", usage_note: "用法说明", domain: "领域", register: "语域", is_core: "核心义项", app_sense_order: "展示顺序",
    translation_zh: "中文译义", translation_en: "英文译义", translations: "译文", translation_id: "译文 ID", lang: "语言代码", gloss: "译义", explanation: "解释",
    forms: "词形", form_type: "词形类型", app_form_role: "词形角色", display_label_zh: "中文标签", display_label_en: "英文标签", morph_features: "形态特征", is_canonical: "标准词形", is_observed: "语料中已观察",
    examples: "义项例句", examples_url: "例句接口", example_id: "例句 ID", ex_nl: "荷文例句", translation: "翻译", quality_score: "质量评分",
    corpus_examples: "语料例句", lemma_example_id: "语料例句 ID", sense_disambiguated: "是否按义项消歧",
    expressions: "表达与构式", expression_id: "表达 ID", entry_kind: "记录类别", expression_type: "表达类型", expression_nl: "荷文表达", gloss_en: "英文译义", gloss_zh: "中文译义", explanation_en: "英文解释", explanation_zh: "中文解释", example_nl: "荷文例句", example_zh: "中文例句",
    sources: "来源", source_id: "来源 ID", source_key: "来源标识", name: "名称", source_type: "来源类型", url: "链接", license: "许可", license_url: "许可链接", attribution: "署名说明", version: "版本", source: "来源",
    relation_type: "关系类型", source_result_lemma_id: "来源结果词头 ID", source_result_sense_id: "来源结果义项 ID",
    items: "条目", total: "总数", offset: "偏移量", limit: "每页数量", has_more: "是否有下一页", next_offset: "下一页偏移量",
  };
  const PAGE_PARAMS = { senses: "sense_", forms: "form_", corpus_examples: "example_", expressions: "expression_" };

  function defaults(endpoint) {
    return Object.fromEntries(Object.entries(ENDPOINTS[endpoint].params).map(([key, value]) => [key, value[0]]));
  }

  function buildRequest(endpoint, query, params) {
    const spec = ENDPOINTS[endpoint];
    if (!spec) throw new Error("未知接口");
    const path = spec.path.replace("{id}", encodeURIComponent(query));
    if (endpoint === "semantic") {
      return { endpoint, query, params: { ...params }, method: spec.method, path, body: { query, ...params } };
    }
    const search = new URLSearchParams(endpoint === "entry" || endpoint === "examples" ? {} : { q: query });
    for (const [key, value] of Object.entries(params)) search.set(key, String(value));
    return { endpoint, query, params: { ...params }, method: spec.method, path, search: search.toString() };
  }

  function requestHash(request) {
    const spec = ENDPOINTS[request.endpoint];
    const isId = request.endpoint === "entry" || request.endpoint === "examples";
    const search = new URLSearchParams(isId ? {} : { q: request.query });
    for (const [key, value] of Object.entries(request.params)) search.set(key, String(value));
    return "#" + spec.route + (isId ? "/" + encodeURIComponent(request.query) : "") + (search.size ? "?" + search : "");
  }

  function parseHash(hash) {
    const raw = hash.replace(/^#/, "") || "/";
    const mark = raw.indexOf("?");
    const path = mark < 0 ? raw : raw.slice(0, mark);
    const search = new URLSearchParams(mark < 0 ? "" : raw.slice(mark + 1));
    for (const [endpoint, spec] of Object.entries(ENDPOINTS)) {
      const isId = endpoint === "entry" || endpoint === "examples";
      if (isId ? !path.startsWith(spec.route + "/") : path !== spec.route) continue;
      const params = defaults(endpoint);
      for (const key of Object.keys(params)) {
        if (!search.has(key)) continue;
        params[key] = typeof params[key] === "boolean" ? search.get(key) === "true" : search.get(key);
      }
      return { endpoint, query: isId ? decodeURIComponent(path.slice(spec.route.length + 1)) : search.get("q") || "", params };
    }
    return { endpoint: "lookup", query: "", params: defaults("lookup") };
  }

  function pageRequest(request, trail, offset, limit) {
    const prefix = request.endpoint === "entry" ? PAGE_PARAMS[trail.join(".")] : request.endpoint === "examples" && trail.join(".") === "examples" ? "" : undefined;
    if (prefix === undefined) return null;
    return buildRequest(request.endpoint, request.query, { ...request.params, [prefix + "offset"]: offset, [prefix + "limit"]: limit });
  }

  // Pure request helpers can be checked with Node, without a DOM or any network.
  if (typeof module !== "undefined" && module.exports) module.exports = { defaults, buildRequest, requestHash, parseHash, pageRequest };
  if (typeof document === "undefined") return;

  const $ = (id) => document.getElementById(id);
  const form = $("query-form"), endpointInput = $("endpoint"), queryInput = $("query");
  const submit = $("submit"), cancel = $("cancel"), notice = $("notice"), responseBody = $("response-body"), responseMeta = $("response-meta");
  const base = (new URLSearchParams(location.search).get("api") || "").replace(/\/+$/, "");
  let active = null, cooldownUntil = 0, cooldownTimer = null;

  function node(tag, text, className) {
    const result = document.createElement(tag);
    if (text !== undefined) result.textContent = String(text);
    if (className) result.className = className;
    return result;
  }

  function message(text, error = false) {
    notice.textContent = text;
    notice.classList.toggle("error", error);
  }

  function updateControls() {
    const wait = Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000));
    submit.disabled = Boolean(active) || wait > 0;
    submit.textContent = active ? "查询中…" : wait > 0 ? `等待 ${wait}s` : "查询";
    endpointInput.disabled = Boolean(active);
    queryInput.disabled = Boolean(active);
    cancel.hidden = !active;
    for (const button of responseBody.querySelectorAll(".pager button")) button.disabled = Boolean(active) || wait > 0;
    if (!wait && cooldownTimer) { clearInterval(cooldownTimer); cooldownTimer = null; }
  }

  function renderParameters(params) {
    const spec = ENDPOINTS[endpointInput.value];
    queryInput.placeholder = spec.placeholder;
    queryInput.inputMode = endpointInput.value === "entry" || endpointInput.value === "examples" ? "numeric" : "text";
    $("input-label").textContent = spec.label;
    $("endpoint-note").textContent = spec.method + " " + spec.path + (base ? " · " + base : "");
    $("parameters").replaceChildren();
    for (const [name, [initial, hint]] of Object.entries(spec.params)) {
      const label = node("label"), input = node("input");
      input.name = name;
      if (typeof initial === "boolean") {
        label.className = "checkbox";
        input.type = "checkbox";
        input.checked = params[name] === true;
        label.append(input, node("span", name + " · " + hint));
      } else {
        input.type = "text";
        input.inputMode = "numeric";
        input.value = params[name] === undefined ? "" : params[name];
        label.append(node("span", name), input, node("small", "API 范围 " + hint));
      }
      $("parameters").append(label);
    }
  }

  function fillForm(request) {
    endpointInput.value = request.endpoint;
    queryInput.value = request.query;
    renderParameters(request.params);
  }

  function readRequest() {
    const endpoint = endpointInput.value, params = {};
    for (const [name, [initial]] of Object.entries(ENDPOINTS[endpoint].params)) {
      const input = form.elements.namedItem(name);
      if (typeof initial === "boolean") params[name] = input.checked;
      else if (input.value !== "") {
        if (endpoint === "semantic") {
          if (!Number.isFinite(Number(input.value))) throw new Error(`${name} 需要数字`);
          params[name] = Number(input.value);
        } else params[name] = input.value;
      }
    }
    // Keep the input, order, duplicates, flags and scores exactly as returned by the API.
    return buildRequest(endpoint, queryInput.value, params);
  }

  function recordAddress(request) {
    const hash = requestHash(request);
    if (location.hash !== hash) history.pushState(null, "", location.pathname + location.search + hash);
  }

  async function run(request) {
    if (active) return;
    if (cooldownUntil > Date.now()) { message("正在等待 Retry-After，请稍后手动查询。", true); return; }
    fillForm(request);
    recordAddress(request);
    const controller = new AbortController();
    active = controller;
    responseMeta.textContent = "请求中";
    responseMeta.classList.remove("error");
    responseBody.replaceChildren(node("p", "正在等待接口响应…", "empty"));
    updateControls();
    message("正在请求 " + request.method + " " + request.path + "…");
    $("response").setAttribute("aria-busy", "true");
    const timeout = setTimeout(() => controller.abort("timeout"), 30000);
    const started = performance.now();
    try {
      const url = base + request.path + (request.search ? "?" + request.search : "");
      const options = { method: request.method, signal: controller.signal, headers: {}, cache: "no-store" };
      if (request.body !== undefined) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(request.body);
      }
      const result = await fetch(url, options);
      const text = await result.text();
      if (controller.signal.aborted) throw new Error("Request aborted");
      let payload;
      try { payload = JSON.parse(text); } catch (_) { payload = text; }
      const retryAfter = result.headers.get("Retry-After");
      const headers = Object.fromEntries(result.headers.entries());
      renderResponse({ request, payload, text, headers, status: result.status, duration: Math.round(performance.now() - started) });
      if (result.status === 429 && retryAfter) {
        const seconds = Number(retryAfter);
        const until = /^\d+$/.test(retryAfter) ? Date.now() + seconds * 1000 : Date.parse(retryAfter);
        if (Number.isFinite(until) && until > Date.now()) {
          cooldownUntil = until;
          if (!cooldownTimer) cooldownTimer = setInterval(updateControls, 1000);
        }
      }
      message(result.ok ? "已显示完整响应；展开条目或原始 JSON 查看全部字段。" : `接口返回 HTTP ${result.status}。错误响应保留原样${retryAfter ? "；Retry-After: " + retryAfter : ""}。`, !result.ok);
    } catch (error) {
      if (controller.signal.aborted) message(controller.signal.reason === "timeout" ? "请求已超时（30 秒），未自动重试。" : "请求已取消。服务端可能已经处理该请求。", true);
      else message("无法连接接口：" + error.message + "。请确认本地服务已启动。", true);
      responseMeta.textContent = "未收到响应";
      responseMeta.classList.add("error");
      responseBody.replaceChildren(node("p", "本次未收到接口响应。", "empty"));
    } finally {
      clearTimeout(timeout);
      active = null;
      $("response").removeAttribute("aria-busy");
      updateControls();
    }
  }

  function endpointLink(value) {
    if (typeof value !== "string") return null;
    let match = /^\/entries\/(\d+)$/.exec(value);
    if (match) return buildRequest("entry", match[1], defaults("entry"));
    match = /^\/senses\/(\d+)\/examples$/.exec(value);
    return match ? buildRequest("examples", match[1], defaults("examples")) : null;
  }

  function scalar(value) {
    if (value === null) return node("span", "null（空值）", "null-value");
    if (typeof value === "string") {
      if (value === "") return node("span", '\"\"（空字符串）', "null-value");
      const request = endpointLink(value);
      if (request) {
        const link = node("a", value);
        link.href = requestHash(request);
        link.addEventListener("click", (event) => {
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
          event.preventDefault();
          run(request);
        });
        return link;
      }
      if (/^https?:\/\//i.test(value)) {
        const link = node("a", value);
        link.href = value; link.target = "_blank"; link.rel = "noopener noreferrer";
        return link;
      }
      return node("span", value);
    }
    return node("span", value, "raw-value");
  }

  function itemTitle(value) {
    if (!value || typeof value !== "object") return "条目";
    return value.lemma || value.definition_nl || value.ex_nl || value.form || value.gloss || value.translation || value.name || value.expression_nl || value.pos || "条目";
  }

  function renderValue(value, trail, request, depth) {
    if (value === null || typeof value !== "object") return scalar(value);
    if (Array.isArray(value)) {
      if (!value.length) return node("span", "[]（空列表）", "null-value");
      const collection = node("div", undefined, "collection");
      collection.append(node("p", value.length + " 项", "collection-count"));
      if (value.every((item) => item === null || typeof item !== "object")) {
        const list = node("ol", undefined, "scalar-list");
        for (const item of value) { const row = node("li"); row.append(scalar(item)); list.append(row); }
        collection.append(list);
      } else value.forEach((item, index) => {
        const details = node("details", undefined, "item"), summary = node("summary");
        details.open = depth <= 1 && ["results", "suggestions", "did_you_mean"].includes(trail.join("."));
        summary.append(node("span", String(index + 1).padStart(2, "0"), "item-number"), node("span", itemTitle(item)));
        if (item && (item.matched_sense || typeof item.definition_nl === "string")) {
          const sense = item.matched_sense || item;
          summary.append(node("span", [sense.translation_zh, sense.translation_en, item.matched_sense ? sense.definition_nl : undefined].filter((text) => text !== undefined && text !== "").join(" · "), "item-summary"));
        }
        const content = node("div", undefined, "item-content");
        content.append(renderValue(item, trail.concat(String(index)), request, depth + 1));
        details.append(summary, content); collection.append(details);
      });
      return collection;
    }
    const fields = node("dl", undefined, "fields");
    if (!Object.keys(value).length) return node("span", "{}（空对象）", "null-value");
    for (const [key, item] of Object.entries(value)) {
      const field = node("div", undefined, "field" + (item !== null && typeof item === "object" ? " complex" : ""));
      const label = node("dt"), content = node("dd");
      if (Object.prototype.hasOwnProperty.call(LABELS, key)) label.append(node("span", LABELS[key]));
      label.append(node("code", key, "field-key"));
      content.append(renderValue(item, trail.concat(key), request, depth + 1));
      field.append(label, content); fields.append(field);
    }
    if (Array.isArray(value.items) && Number.isInteger(value.offset) && Number.isInteger(value.limit) && value.limit > 0) {
      const pager = node("div", undefined, "pager");
      const addPage = (offset, title) => {
        const next = pageRequest(request, trail, offset, value.limit);
        if (!next) return;
        const button = node("button", title + ` · offset=${offset}`);
        button.type = "button";
        button.addEventListener("click", () => run(next));
        pager.append(button);
      };
      if (value.offset > 0) addPage(Math.max(0, value.offset - value.limit), "上一页");
      if (value.has_more && Number.isInteger(value.next_offset)) addPage(value.next_offset, "下一页");
      if (pager.childElementCount) {
        const group = document.createDocumentFragment();
        group.append(fields, pager);
        return group;
      }
    }
    return fields;
  }

  function renderResponse(result) {
    responseMeta.textContent = `HTTP ${result.status} · ${result.duration} ms`;
    responseMeta.classList.toggle("error", result.status >= 400);
    const info = node("div", undefined, "request-info");
    info.append(node("div", result.request.method + " " + base + result.request.path + (result.request.search ? "?" + result.request.search : ""), "request-url"));
    if (result.request.body !== undefined) {
      const requestBody = node("details", undefined, "request-body");
      requestBody.append(node("summary", "请求体"), node("pre", JSON.stringify(result.request.body, null, 2)));
      info.append(requestBody);
    }
    const raw = node("details", undefined, "raw-json"), toolbar = node("div", undefined, "raw-toolbar");
    const copy = node("button", "复制响应体");
    copy.type = "button";
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(result.text); message("已复制接口原始响应体。"); }
      catch (_) { message("复制失败，可展开原始 JSON 后手动选择。", true); }
    });
    toolbar.append(copy);
    const headers = node("details");
    headers.append(node("summary", "响应头"), node("pre", JSON.stringify(result.headers, null, 2)));
    raw.append(node("summary", "原始 JSON / 响应体"), toolbar, node("pre", result.text), headers);
    responseBody.replaceChildren(info, renderValue(result.payload, [], result.request, 0), raw);
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    try { run(readRequest()); } catch (error) { message(error.message, true); }
  });
  endpointInput.addEventListener("change", () => {
    renderParameters(defaults(endpointInput.value));
    message(endpointInput.value === "semantic" ? "提交后调用语义接口；不会随着输入自动查询。" : "输入内容后点击查询。每次提交只请求所选接口。");
  });
  cancel.addEventListener("click", () => { if (active) active.abort("cancelled"); });
  document.querySelector(".skip-link").addEventListener("click", (event) => {
    event.preventDefault();
    $("main").focus();
  });
  window.addEventListener("hashchange", () => {
    if (active) active.abort("navigated");
    try { fillForm(parseHash(location.hash)); message("地址已载入，请点击查询发送请求。"); }
    catch (_) { message("无法读取查询地址，请重新输入。", true); }
  });
  try { fillForm(parseHash(location.hash)); } catch (_) { fillForm({ endpoint: "lookup", query: "", params: defaults("lookup") }); }
})();
