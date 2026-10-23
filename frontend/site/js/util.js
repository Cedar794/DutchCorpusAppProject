/* ==========================================================================
   Woordhuis · util
   DOM builders, icons, formatting, small platform helpers.
   All remote text goes in through text nodes — never innerHTML.
   ========================================================================== */
(function () {
  "use strict";

  const WH = (window.WH = window.WH || {});

  /* ---------------------------------------------------------------- DOM -- */

  function el(spec, props, ...children) {
    const m = /^([a-zA-Z][a-zA-Z0-9-]*)?((?:[.#][\w-]+)*)$/.exec(spec || "div");
    if (!m) throw new Error("bad element spec: " + spec);
    const tag = m[1] || "div";
    const node = document.createElement(tag);
    if (m[2]) {
      for (const part of m[2].match(/[.#][\w-]+/g) || []) {
        if (part[0] === ".") node.classList.add(part.slice(1));
        else node.id = part.slice(1);
      }
    }
    if (props) applyProps(node, props);
    append(node, children);
    return node;
  }

  function applyProps(node, props) {
    for (const [key, value] of Object.entries(props)) {
      if (value === null || value === undefined || value === false) continue;
      switch (key) {
        case "class":
        case "className": {
          for (const cls of String(value).split(/\s+/)) if (cls) node.classList.add(cls);
          break;
        }
        case "text":
          node.textContent = String(value);
          break;
        case "html":
          // trusted constants only (never remote data)
          node.innerHTML = value;
          break;
        case "style":
          if (typeof value === "string") node.style.cssText = value;
          else for (const [k, v] of Object.entries(value)) node.style.setProperty(k, v);
          break;
        case "dataset":
          for (const [k, v] of Object.entries(value)) if (v != null) node.dataset[k] = String(v);
          break;
        case "attrs":
          for (const [k, v] of Object.entries(value)) {
            if (v === false || v === null || v === undefined) node.removeAttribute(k);
            else node.setAttribute(k, String(v));
          }
          break;
        case "aria":
          for (const [k, v] of Object.entries(value)) {
            if (v === false || v === null || v === undefined) node.removeAttribute("aria-" + k);
            else node.setAttribute("aria-" + k, String(v));
          }
          break;
        default:
          if (key.startsWith("on") && typeof value === "function") {
            node.addEventListener(key.slice(2).toLowerCase(), value);
          } else if (key === "value" || key === "checked" || key === "disabled" || key === "hidden") {
            node[key] = value;
          } else {
            node.setAttribute(key, String(value));
          }
      }
    }
  }

  function append(node, children) {
    for (const child of children) {
      if (child === null || child === undefined || child === false || child === "") continue;
      if (Array.isArray(child)) append(node, child);
      else if (child instanceof Node) node.appendChild(child);
      else node.appendChild(document.createTextNode(String(child)));
    }
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
    return node;
  }

  function frag(...children) {
    return append(document.createDocumentFragment(), children);
  }

  /* -------------------------------------------------------------- icons -- */

  const ICONS = {
    search: { vb: "0 0 24 24", d: ["M10.8 18.1a7.3 7.3 0 1 0 0-14.6 7.3 7.3 0 0 0 0 14.6Z", "m16.2 16.2 4.3 4.3"] },
    arrowLeft: { vb: "0 0 24 24", d: ["M20 12H4", "m10 6-6 6 6 6"] },
    arrowRight: { vb: "0 0 24 24", d: ["M4 12h16", "m14 6 6 6-6 6"] },
    arrowUpRight: { vb: "0 0 24 24", d: ["M7 17 17 7", "M8 7h9v9"] },
    close: { vb: "0 0 24 24", d: ["M6 6l12 12", "M18 6 6 18"] },
    copy: { vb: "0 0 24 24", d: ["M9 9h10v10H9z", "M5 15V5h10"] },
    external: { vb: "0 0 24 24", d: ["M14 4h6v6", "M20 4 11 13", "M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"] },
    info: { vb: "0 0 24 24", d: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 11v6", "M12 7.6v.2"] },
    alert: { vb: "0 0 24 24", d: ["M12 3 2.6 20h18.8L12 3Z", "M12 9v5", "M12 17.4v.2"] },
    clock: { vb: "0 0 24 24", d: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 7v5.2l3.4 2"] },
    book: { vb: "0 0 24 24", d: ["M4 5.5A1.5 1.5 0 0 1 5.5 4H19v16H5.5A1.5 1.5 0 0 1 4 18.5v-13Z", "M4 17h15", "M8 4v7l2-1.4L12 11V4"] },
    bookmark: { vb: "0 0 24 24", d: ["M6 4h12v17l-6-4.2L6 21V4Z"] },
    bookmarkOn: { vb: "0 0 24 24", fill: true, d: ["M6 4h12v17l-6-4.2L6 21V4Z"] },
    sun: { vb: "0 0 24 24", d: ["M12 16.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9Z", "M12 2v2.2M12 19.8V22M2 12h2.2M19.8 12H22M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M19.1 4.9l-1.6 1.6M6.5 17.5l-1.6 1.6"] },
    moon: { vb: "0 0 24 24", d: ["M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"] },
    check: { vb: "0 0 24 24", d: ["m4 12.5 5 5L20 6.5"] },
    chevronDown: { vb: "0 0 24 24", d: ["m6 9.5 6 6 6-6"] },
    layers: { vb: "0 0 24 24", d: ["m12 3 9 5-9 5-9-5 9-5Z", "m3 13 9 5 9-5"] },
    sliders: { vb: "0 0 24 24", d: ["M4 7h10M18 7h2M4 17h4M12 17h8", "M14 7a2 2 0 1 0 4 0 2 2 0 0 0-4 0ZM8 17a2 2 0 1 0 4 0 2 2 0 0 0-4 0Z"] },
    quote: { vb: "0 0 24 24", d: ["M9 6H5v6h4c0 3-1.4 4.6-4 6", "M19 6h-4v6h4c0 3-1.4 4.6-4 6"] },
    windmill: {
      vb: "0 0 64 64",
      sw: 1.6,
      d: [
        ["M24 57 28.5 32h7L40 57Z", 1.6],
        ["M28 32c0-5 8-5 8 0", 1.6],
        ["M32 26.6a2 2 0 1 0 .01 0Z", 1.5],
        ["M32 28 18 14", 2.6],
        ["M32 28 46 14", 2.6],
        ["M32 28 18.5 41.5", 2.6],
        ["M32 28 45.5 41.5", 2.6],
        ["M30.8 39.5h2.4v3.4h-2.4Z", 1.3],
        ["M29.5 57v-6.4h5V57", 1.4],
        ["M12 58.5h40", 1.2],
      ],
    },
    gable: {
      vb: "0 0 24 24",
      sw: 1.5,
      d: ["M4 21V11.5L12 4l8 7.5V21", "M10 21v-5.5h4V21"],
    },
    medallion: {
      vb: "0 0 24 24",
      sw: 1,
      d: [
        "M12 3.4 20.6 12 12 20.6 3.4 12Z",
        "M12 9.2a2.8 2.8 0 1 0 0 5.6 2.8 2.8 0 0 0 0-5.6Z",
        "M12 3.4v3.4M12 17.2v3.4M3.4 12h3.4M17.2 12h3.4",
      ],
    },
    tile: {
      vb: "0 0 24 24",
      sw: 1.2,
      d: ["M3 3h18v18H3z", "M12 7.4c1.9 0 3.4 1.4 3.4 3.1S13.9 13.6 12 13.6 8.6 12.2 8.6 10.5 10.1 7.4 12 7.4Z", "M12 13.6v3"],
    },
    flag: {
      vb: "0 0 24 24",
      sw: 1.4,
      d: ["M5 3v18", "M5 4h14l-2.4 4L19 12H5"],
    },
  };

  function icon(name, opts = {}) {
    const spec = ICONS[name];
    if (!spec) return el("span");
    const size = opts.size || 20;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", spec.vb);
    svg.setAttribute("width", opts.width || size);
    svg.setAttribute("height", opts.height || size);
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("fill", spec.fill ? "currentColor" : "none");
    svg.setAttribute("stroke", spec.fill ? "none" : "currentColor");
    svg.setAttribute("stroke-width", spec.sw || 1.6);
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    if (opts.class) svg.setAttribute("class", opts.class);
    for (const item of spec.d) {
      const [d, weight] = Array.isArray(item) ? item : [item, null];
      const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
      p.setAttribute("d", d);
      if (weight) p.setAttribute("stroke-width", String(weight));
      svg.appendChild(p);
    }
    return svg;
  }

  /* ---------------------------------------------------------- formatting -- */

  const nf = new Intl.NumberFormat("zh-CN");

  const fmt = {
    num(n) {
      return typeof n === "number" && isFinite(n) ? nf.format(n) : "—";
    },
    /** scores are internal ranking values, not probabilities. 3 decimals max. */
    score(n) {
      if (typeof n !== "number" || !isFinite(n)) return "—";
      return n.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
    },
    /** 0-1 confidence shown as a percentage bar but labelled as heuristic */
    conf(n) {
      if (typeof n !== "number" || !isFinite(n)) return "—";
      return Math.round(n * 100) + "%";
    },
    level(level) {
      return level ? "L" + level : "L?";
    },
    date(iso) {
      if (!iso) return "";
      const d = new Date(iso);
      if (isNaN(d)) return "";
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
        d.getDate()
      ).padStart(2, "0")}`;
    },
    ms(n) {
      if (typeof n !== "number") return "";
      return n >= 1000 ? (n / 1000).toFixed(1) + " s" : Math.round(n) + " ms";
    },
  };

  const LABELS = {
    match: {
      form_exact: "词形完全匹配",
      lemma_exact: "词头完全匹配",
      lemma_fuzzy: "词头近似",
      form_fuzzy: "词形近似",
      exact: "完全匹配",
      fuzzy: "近似匹配",
    },
    review: { accepted: "已审核", needs_review: "待复核", unreviewed: "未复核" },
    reviewShort: { accepted: "已审核", needs_review: "待复核", unreviewed: "未复核" },
    kind: {
      lexical_expression: "词汇表达",
      usage_construction: "语法构式",
      definition_note: "释义说明",
      usage_example: "用例",
    },
    kindDesc: {
      lexical_expression: "作为固定单位使用的词组，意义不等于各词相加。",
      usage_construction: "句法构式：某个结构在特定语境中的用法。",
      definition_note: "释义补充：帮助理解该义项的说明性短语。",
      usage_example: "用例：来源中的一次性搭配，不是固定说法。",
    },
    relation: {
      family_head: "词族中心",
      same_synset: "同义集",
      derived: "派生",
      related: "相关",
    },
    rewrite: {
      rewritten: "已改写用于检索",
      unchanged: "改写后保留原文",
      disabled: "改写未启用，按原文检索",
      unconfigured: "改写未配置，按原文检索",
      timeout: "改写超时，已按原文检索",
      provider_error: "改写服务报错，已按原文检索",
      circuit_open: "改写熔断，已按原文检索",
      busy: "改写繁忙，已按原文检索",
      budget_unavailable: "改写额度不可用，已按原文检索",
      invalid_or_unavailable: "改写结果不可用，已按原文检索",
      constraint_fallback: "改写丢失约束，已回退原文",
    },
    sourceType: {
      manual: "人工整理",
      corpus_frequency: "语料频次",
      lexical_semantic: "词汇语义库",
      wiktionary_extract: "维基词典抽取",
      llm_derived: "模型生成",
      aigc_derived: "AIGC 生成",
      corpus_derived: "语料抽取",
      dictionary: "纸质词典",
    },
    pos: {
      noun: "名词",
      verb: "动词",
      adjective: "形容词",
      adverb: "副词",
      special: "特殊词类",
      pronoun: "代词",
      preposition: "介词",
      conjunction: "连词",
      numeral: "数词",
      article: "冠词",
      interjection: "感叹词",
    },
    article: { de: "de（通性）", het: "het（中性）" },
    gender: { common: "通性", neuter: "中性", masculine: "阳性", feminine: "阴性" },
  };

  /** pick the display gloss of a sense for the chosen UI language */
  function senseGloss(sense, lang) {
    if (lang === "nl") return sense.definition_nl || "";
    if (lang === "en") return sense.translation_en || sense.translation_zh || "";
    return sense.translation_zh || sense.translation_en || "";
  }

  function senseSecondary(sense, lang) {
    if (lang === "zh") return sense.translation_en || "";
    if (lang === "en") return sense.translation_zh || "";
    return sense.translation_zh || sense.translation_en || "";
  }

  function posLabel(pos, lang) {
    if (!pos) return "";
    if (lang === "zh") return pos.label_zh || LABELS.pos[pos.app_pos] || pos.app_pos || pos.pos;
    if (lang === "en") return pos.label_en || pos.app_pos || pos.pos;
    return pos.label_nl || pos.app_pos || pos.pos;
  }

  function formLabel(form, lang) {
    if (lang === "zh") return form.display_label_zh || form.form_type || "";
    if (lang === "en") return form.display_label_en || form.form_type || "";
    return form.form_type || form.display_label_en || "";
  }

  function exampleTranslation(example, lang) {
    if (!example || !example.translations || !example.translations.length) return "";
    const wanted = lang === "nl" ? "en" : lang;
    const hit = example.translations.find((t) => t.lang === wanted);
    if (hit) return hit.translation;
    const first = example.translations[0];
    return first ? first.translation : "";
  }

  /* ------------------------------------------------------------ storage -- */

  const storage = {
    get(key, fallback) {
      try {
        const raw = localStorage.getItem("woordhuis:" + key);
        return raw === null ? fallback : JSON.parse(raw);
      } catch (e) {
        return fallback;
      }
    },
    set(key, value) {
      try {
        localStorage.setItem("woordhuis:" + key, JSON.stringify(value));
      } catch (e) {
        /* private mode: ignore */
      }
    },
  };

  /* ------------------------------------------------------------- helpers -- */

  function debounce(fn, wait) {
    let t = 0;
    const wrapped = (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), wait);
    };
    wrapped.cancel = () => clearTimeout(t);
    return wrapped;
  }

  /** mark every occurrence of any of `words` inside `text` (already a string) */
  function highlight(text, words) {
    const list = (words || []).filter((w) => w && w.length > 1).map(escapeRe);
    if (!list.length) return document.createTextNode(text);
    // longest first so "huizen" wins over "huis"
    list.sort((a, b) => b.length - a.length);
    const re = new RegExp("(" + list.join("|") + ")", "gi");
    const out = document.createDocumentFragment();
    let last = 0;
    let m;
    while ((m = re.exec(text))) {
      if (m.index > last) out.appendChild(document.createTextNode(text.slice(last, m.index)));
      const mark = document.createElement("mark");
      mark.textContent = m[0];
      out.appendChild(mark);
      last = m.index + m[0].length;
      if (re.lastIndex === m.index) re.lastIndex++;
    }
    if (last < text.length) out.appendChild(document.createTextNode(text.slice(last)));
    return out;
  }

  const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      // file:// or denied clipboard permission
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      let ok = false;
      try {
        ok = document.execCommand("copy");
      } catch (err) {
        ok = false;
      }
      document.body.removeChild(area);
      return ok;
    }
  }

  let toastTimer = 0;
  function toast(message) {
    let host = document.querySelector(".toast-host");
    if (!host) {
      host = el("div.toast-host", { attrs: { role: "status", "aria-live": "polite" } });
      document.body.appendChild(host);
    }
    clear(host);
    host.appendChild(el("div.toast", null, message));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => clear(host), 2200);
  }

  /** wrap the Dutch IJ digraph in the given text with a marked span */
  function withDigraph(text) {
    const frag = document.createDocumentFragment();
    const re = /(ij|IJ|IJ|ĳ|Ĳ)/g;
    let last = 0;
    let m;
    while ((m = re.exec(text))) {
      if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      const span = document.createElement("span");
      span.className = "digraph-ij";
      span.textContent = m[0];
      frag.appendChild(span);
      last = m.index + m[0].length;
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    return frag;
  }

  function includesIj(word) {
    return /ij/i.test(word || "");
  }

  WH.el = el;
  WH.clear = clear;
  WH.dom = { el, clear, frag, append };
  WH.icon = icon;
  WH.fmt = fmt;
  WH.labels = LABELS;
  WH.senseGloss = senseGloss;
  WH.senseSecondary = senseSecondary;
  WH.posLabel = posLabel;
  WH.formLabel = formLabel;
  WH.exampleTranslation = exampleTranslation;
  WH.storage = storage;
  WH.debounce = debounce;
  WH.highlight = highlight;
  WH.copy = copy;
  WH.toast = toast;
  WH.withDigraph = withDigraph;
  WH.includesIj = includesIj;
})();
