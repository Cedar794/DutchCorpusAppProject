/* ==========================================================================
   Woordhuis · api
   Two transports behind one interface:
     • http  — the real FastAPI contract (same-origin or ?api=<base>)
     • demo  — replay of the 69 responses recorded on 2026-10-23
   Demo matching mirrors mock_server.py, with one addition: a recorded page can
   serve a sub-range of itself, so paging stays coherent inside the recording.
   ========================================================================== */
(function () {
  "use strict";

  const WH = (window.WH = window.WH || {});

  class ApiError extends Error {
    constructor(status, detail, retryAfter, kind) {
      super("Dictionary API " + status);
      this.status = status;
      this.detail = detail;
      this.retryAfter = retryAfter || null;
      this.kind = kind || classify(status, detail);
    }
  }

  function classify(status, detail) {
    if (status === 0) return "network";
    if (status === 404) return "not_found";
    if (status === 413) return "too_large";
    if (status === 422) return "invalid";
    if (status === 429) return "rate";
    if (status >= 500) return "unavailable";
    if (status === 501) return "not_recorded";
    return "unknown";
  }

  const ENTRY_DEFAULTS = {
    sense_offset: "0",
    sense_limit: "20",
    form_offset: "0",
    form_limit: "50",
    example_offset: "0",
    example_limit: "5",
    expression_offset: "0",
    expression_limit: "20",
  };

  function defaultsFor(path) {
    if (path === "/lookup") return { limit: "5" };
    if (path === "/suggest") return { limit: "10" };
    if (path.startsWith("/entries/")) return { ...ENTRY_DEFAULTS };
    if (path.startsWith("/senses/")) return { offset: "0", limit: "10" };
    return {};
  }

  /* ------------------------------------------------------------------ demo */

  const demo = {
    scenarios: [],
    bodies: {},
    forced: null,

    init() {
      const fixtures = window.WH.FIXTURES;
      if (!fixtures) return false;
      this.scenarios = fixtures.scenarios || [];
      this.bodies = window.WH.FIXTURE_BODIES || {};
      return this.scenarios.length > 0;
    },

    bodyOf(scenario) {
      return this.bodies[scenario.body];
    },

    /** exact request match, like mock_server.py */
    find({ method, path, query, json, rawLength }) {
      if (this.forced) {
        const hit = this.scenarios.find((s) => s.id === this.forced);
        if (hit) return hit;
      }
      const defaults = defaultsFor(path);
      const actualQuery = {};
      for (const [k, v] of Object.entries({ ...defaults, ...(query || {}) })) {
        actualQuery[k] = String(v);
      }
      const candidates = this.scenarios.filter((s) => {
        if (s.method !== method || s.path !== path) return false;
        if (method === "GET") {
          const recorded = { ...defaults, ...(s.query || {}) };
          const a = Object.keys(recorded).sort().join();
          const b = Object.keys(actualQuery).sort().join();
          if (a !== b) return false;
          return Object.keys(recorded).every(
            (k) => String(recorded[k]) === String(actualQuery[k])
          );
        }
        if (s.raw_body_8193) return rawLength === 8193;
        const recorded = { ...(s.json || {}) };
        const actual = { ...(json || {}) };
        if (path === "/semantic-search") {
          if (recorded.limit == null) recorded.limit = 10;
          if (recorded.include_related == null) recorded.include_related = true;
          if (actual.limit == null) actual.limit = 10;
          if (actual.include_related == null) actual.include_related = true;
        }
        return JSON.stringify(sortKeys(recorded)) === JSON.stringify(sortKeys(actual));
      });
      if (!candidates.length) return null;
      candidates.sort((a, b) => {
        const score = (s) => (s.default_replay ? 0 : 2) + (s.status !== 200 ? 1 : 0);
        return score(a) - score(b) || a.id.localeCompare(b.id);
      });
      return candidates[0];
    },

    /** serve a sub-range of a recorded page when the exact page is absent */
    slicePage({ path, query, base, prefix }) {
      const wantOffset = Number(query[prefix + "offset"] || 0);
      const wantLimit = Number(query[prefix + "limit"] || 20);
      const pools = [];
      for (const s of this.scenarios) {
        if (s.method !== "GET" || s.path !== path || s.status !== 200) continue;
        const body = this.bodyOf(s);
        const page = body && base(body);
        if (!page || !Array.isArray(page.items)) continue;
        const off = Number((s.query && s.query[prefix + "offset"]) || 0);
        pools.push({ start: off, items: page.items, page });
      }
      for (const pool of pools) {
        const end = pool.start + pool.items.length;
        if (wantOffset >= pool.start && wantOffset < end) {
          const from = wantOffset - pool.start;
          const slice = pool.items.slice(from, from + wantLimit);
          return {
            ...pool.page,
            items: slice,
            offset: wantOffset,
            limit: wantLimit,
            total: pool.page.total,
            has_more: wantOffset + slice.length < pool.page.total,
            next_offset:
              wantOffset + slice.length < pool.page.total ? wantOffset + slice.length : null,
          };
        }
      }
      return null;
    },

    respond(req) {
      const hit = this.find(req);
      if (hit) {
        return { status: hit.status, headers: hit.headers || {}, body: this.bodyOf(hit), scenario: hit };
      }
      // sub-range fallback for the four paged groups of an entry
      if (req.method === "GET" && req.path.startsWith("/entries/")) {
        const q = { ...ENTRY_DEFAULTS, ...(req.query || {}) };
        const body = {};
        let touched = false;
        for (const [prefix, key] of [
          ["sense_", "senses"],
          ["form_", "forms"],
          ["example_", "corpus_examples"],
          ["expression_", "expressions"],
        ]) {
          const page = this.slicePage({
            path: req.path,
            query: q,
            base: (b) => b[key],
            prefix,
          });
          if (page) {
            body[key] = page;
            touched = true;
          }
        }
        if (touched) {
          const template = this.scenarios
            .map((s) => this.bodyOf(s))
            .find((b) => b && b.lemma_id && String(b.lemma_id) === req.path.split("/")[2]);
          if (template) return { status: 200, headers: {}, body: { ...template, ...body } };
        }
      }
      if (req.method === "GET" && req.path.startsWith("/senses/")) {
        const page = this.slicePage({
          path: req.path,
          query: req.query || {},
          base: (b) => b.examples,
          prefix: "",
        });
        if (page) {
          const template = this.scenarios
            .map((s) => this.bodyOf(s))
            .find((b) => b && b.sense_id && String(b.sense_id) === req.path.split("/")[2]);
          return {
            status: 200,
            headers: {},
            body: { ...(template || { sense_id: Number(req.path.split("/")[2]) }), examples: page },
          };
        }
      }
      return {
        status: 501,
        headers: {},
        body: {
          detail:
            "No captured fixture matches this request — the offline recording has no response for it.",
        },
        scenario: null,
      };
    },
  };

  function sortKeys(obj) {
    const out = {};
    for (const key of Object.keys(obj).sort()) out[key] = obj[key];
    return out;
  }

  /* ------------------------------------------------------------------ http */

  const config = {
    mode: "http", // served pages use the real same-origin API; ?mode=demo replays fixtures
    base: "",
    timeout: 15000,
  };

  function resolveConfig() {
    const params = new URLSearchParams(location.search);
    const fromQuery = params.get("api");
    if (params.get("mode") === "demo" || location.protocol === "file:") {
      config.base = "";
      config.mode = "demo";
    } else if (fromQuery !== null) {
      config.base = fromQuery.replace(/\/+$/, "");
      config.mode = "http";
      WH.storage.set("apiBase", config.base);
    } else {
      config.base = "";
      config.mode = "http";
    }
    if (!demo.init() && config.mode === "demo") {
      config.mode = "http";
      config.base = "";
    }
  }

  async function httpRequest(method, path, { query, body, signal, timeout } = {}) {
    const qs = query && Object.keys(query).length ? "?" + new URLSearchParams(query).toString() : "";
    const url = config.base + path + qs;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort("timeout"), timeout || config.timeout);
    const relay = () => controller.abort("navigated");
    if (signal) {
      if (signal.aborted) relay();
      else signal.addEventListener("abort", relay, { once: true });
    }
    try {
      const init = { method, signal: controller.signal, headers: {} };
      if (body !== undefined) {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(body);
      }
      const response = await fetch(url, init);
      const type = response.headers.get("Content-Type") || "";
      const payload = type.includes("application/json") ? await response.json() : await response.text();
      if (!response.ok) {
        const retryHeader = response.headers.get("Retry-After");
        const retry = retryHeader && isFinite(Number(retryHeader)) ? Number(retryHeader) : null;
        const detail = typeof payload === "object" && payload !== null ? payload.detail : payload;
        throw new ApiError(response.status, detail, retry);
      }
      return payload;
    } catch (err) {
      if (err instanceof ApiError) throw err;
      if (controller.signal.aborted) {
        const reason = controller.signal.reason;
        if (reason === "timeout") throw new ApiError(0, "请求超时", null, "timeout");
        throw new ApiError(0, "已取消", null, "aborted");
      }
      throw new ApiError(0, "无法连接接口：" + (err && err.message ? err.message : "未知错误"), null, "network");
    } finally {
      clearTimeout(timer);
      if (signal) signal.removeEventListener("abort", relay);
    }
  }

  function demoRequest(method, path, { query, body }) {
    return new Promise((resolve, reject) => {
      const result = demo.respond({
        method,
        path,
        query: query || {},
        json: body,
        rawLength: body ? JSON.stringify(body).length : 0,
      });
      // a small, honest delay so loading states are visible and testable
      setTimeout(() => {
        if (result.status >= 400) {
          const detail =
            result.body && typeof result.body === "object" ? result.body.detail : result.body;
          const retry = result.headers && result.headers["Retry-After"];
          reject(
            new ApiError(
              result.status,
              detail,
              retry ? Number(retry) : null,
              result.status === 501 ? "not_recorded" : undefined
            )
          );
        } else {
          resolve(result.body);
        }
      }, 90 + Math.random() * 120);
    });
  }

  function request(method, path, options = {}) {
    if (config.mode === "http") return httpRequest(method, path, options);
    return demoRequest(method, path, options);
  }

  /* ------------------------------------------------------------- endpoints */

  const api = {
    get mode() {
      return config.mode;
    },
    get base() {
      return config.base;
    },
    ApiError,

    init: resolveConfig,

    useHttp(base) {
      config.base = (base || "").replace(/\/+$/, "");
      config.mode = "http";
      WH.storage.set("apiBase", config.base);
    },
    useDemo() {
      config.mode = "demo";
      WH.storage.set("apiBase", "");
    },

    lookup(q, signal) {
      return request("GET", "/lookup", { query: { q, limit: 5 }, signal });
    },
    suggest(q, signal, limit = 10) {
      return request("GET", "/suggest", { query: { q, limit }, signal });
    },
    entry(id, pagination = {}, signal) {
      return request("GET", "/entries/" + encodeURIComponent(id), {
        query: pagination,
        signal,
        timeout: 20000,
      });
    },
    examples(senseId, offset = 0, limit = 10, signal) {
      return request("GET", `/senses/${encodeURIComponent(senseId)}/examples`, {
        query: { offset, limit },
        signal,
      });
    },
    semantic(input, signal) {
      return request("POST", "/semantic-search", {
        body: {
          query: input.query,
          limit: input.limit == null ? 10 : input.limit,
          include_related: input.include_related !== false,
        },
        signal,
        timeout: 30000,
      });
    },

    /* inspector hooks ---------------------------------------------------- */
    scenarios() {
      return demo.scenarios;
    },
    forceScenario(id) {
      demo.forced = id || null;
    },
    get forcedScenario() {
      return demo.forced;
    },
    recordedAt() {
      return (window.WH.FIXTURES && window.WH.FIXTURES.recorded_at) || null;
    },
  };

  /* --------------------------------------------------- error presentation -- */

  /** turn any thrown value into a plain description the UI can render */
  function describeError(err) {
    const status = err && err.status;
    const detail = err && err.detail;

    if (!err || status === undefined) {
      return { code: "错误", title: "出了点问题", text: "请稍后再试。", kind: "unknown" };
    }
    if (err.kind === "network") {
      return { code: "网络", title: "连不上接口", text: "检查 API 地址或同源代理。", kind: "network" };
    }
    if (err.kind === "timeout") {
      return { code: "超时", title: "请求超时", text: "语义查询不自动重试。", kind: "timeout" };
    }
    if (err.kind === "aborted") {
      return { code: "已取消", title: "请求已取消", text: "", kind: "aborted" };
    }
    if (status === 404) {
      return { code: "404", title: "词条不存在", text: "可能已删除、待核或未公开。", kind: "not_found" };
    }
    if (status === 413) {
      return { code: "413", title: "输入太长", text: "请求体上限 8 KiB。", kind: "too_large" };
    }
    if (status === 422) {
      const list = Array.isArray(detail) ? detail : null;
      return {
        code: "422",
        title: "参数不合法",
        text: list
          ? list.map((d) => `${(d.loc || []).join(" › ")}：${d.msg}`).join("\n")
          : String(detail || "服务端拒绝了这次请求的参数。"),
        kind: "invalid",
        detail,
      };
    }
    if (status === 429) {
      return {
        code: "429",
        title: "请求过于频繁",
        text: "60 次/分钟 · 10 秒最多 10 次 · 语义 10 次/分钟。已加载内容仍可阅读。",
        kind: "rate",
        retryAfter: err.retryAfter,
      };
    }
    if (status === 503) {
      const disabled = /semantic search is not enabled/i.test(String(detail || ""));
      return {
        code: "503",
        title: disabled ? "语义搜索未开启" : "服务暂不可用",
        text: disabled ? "可改用普通查词。" : "稍后重试；普通查词不受影响。",
        kind: "unavailable",
        semanticDisabled: disabled,
      };
    }
    if (status === 501) {
      return {
        code: "离线",
        title: "这条请求没有录制",
        text: "共 69 条录制响应；接真实接口可查全量。",
        kind: "not_recorded",
      };
    }
    return {
      code: String(status),
      title: "接口返回了错误",
      text: typeof detail === "string" ? detail : JSON.stringify(detail),
      kind: "unknown",
    };
  }

  WH.api = api;
  WH.describeError = describeError;
})();
