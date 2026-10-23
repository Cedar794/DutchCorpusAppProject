/* ==========================================================================
   Woordhuis · home
   ========================================================================== */
(function () {
  "use strict";

  const WH = (window.WH = window.WH || {});
  const { el, icon } = WH;
  const ui = WH.ui;

  /* words with a recorded response in this package; the numbers are the API's
     own totals, the definition is the first source definition, verbatim. */
  const TILES = [
    { id: 138, lemma: "huis", level: 1, senses: 13, forms: 34, def: "woning" },
    { id: 1, lemma: "zijn", level: 1, senses: 26, forms: 72, def: "wezen" },
    { id: 8, lemma: "hebben", level: 1, senses: 26, forms: 36, def: "bezitten" },
    { id: 21, lemma: "kunnen", level: 1, senses: 15, forms: 34, def: "het vermogen om iets te doen" },
    { id: 34, lemma: "komen", level: 1, senses: 17, forms: 37, def: "punt bereiken" },
    { id: 36, lemma: "goed", level: 1, senses: 17, forms: 51, def: "dat wat goed is" },
    { id: 44, lemma: "zeggen", level: 1, senses: 10, forms: 37, def: "in gesproken woorden uiten" },
    { id: 51, lemma: "zien", level: 1, senses: 16, forms: 34, def: "met je ogen waarnemen" },
    { id: 2327, lemma: "afzetten", level: 1, senses: 33, forms: 15, def: "van het hoofd of lichaam verwijderen" },
    { id: 662, lemma: "ontdekken", level: 1, senses: 7, forms: 21, def: "vinden wat verborgen is" },
  ];

  const SPECIMEN = [
    { no: "1", nl: "woning", zh: "家" },
    { no: "1", nl: "(woning) gebouw bestemd om in te wonen", zh: "（建筑）" },
    { no: "2", nl: "iemands woonplek", zh: "某人的居住地" },
    { no: "3", nl: "gebouw", zh: "建筑" },
    { no: "4", nl: "geslacht van mensen", zh: "人的性别" },
    { no: "5", nl: "dat wat dient om te omhullen", zh: "用来包裹的东西" },
  ];

  const LOOKUP_SAMPLES = [
    { label: "huis", q: "huis" },
    { label: "huizen", q: "huizen", hint: "词形" },
    { label: "huiss", q: "huiss", hint: "拼错" },
    { label: "afzetten", q: "afzetten" },
  ];

  /* verbatim recorded requests, so the offline recording can answer them */
  const SEMANTIC_SAMPLES = [
    { label: "可以借书的地方", q: "不是书店，而是可以借书的地方，想找一个名词。", tag: "zh" },
    { label: "人们吃的东西", q: "我想找一个名词，意思是人们吃的食物。", tag: "zh" },
    { label: "看不见的东西", q: "请找一个形容词，表示某个东西不能被看见。", tag: "zh" },
    { label: "骑的两轮车", q: "a noun for a vehicle with 2 wheels that you pedal, not a motorbike", tag: "en" },
  ];

  /* a stylised row of canal-house gables (trap-, klok-, tuit- en lijstgevel) */
  const SKYLINE = `
<svg viewBox="0 0 1600 160" preserveAspectRatio="xMidYMax meet" aria-hidden="true"
  fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
  <defs>
    <g id="h-trap">
      <path d="M6 160V74h24V62h24V50h18V32h56v18h18v12h24v12h24v74"/>
      <path d="M50 92h14v18H50zM96 92h14v18H96zM136 92h14v18h-14z" stroke-width="1.1" opacity=".65"/>
      <path d="M84 134h18v26H84z" stroke-width="1.2"/>
    </g>
    <g id="h-klok">
      <path d="M6 160V72h20c12 0 16-12 22-24C58 28 74 14 100 10c26 4 42 18 52 38 6 12 10 24 22 24h20v88"/>
      <path d="M64 96h14v20H64zM122 96h14v20h-14z" stroke-width="1.1" opacity=".65"/>
      <path d="M90 132h20v28H90z" stroke-width="1.2"/>
    </g>
    <g id="h-tuit">
      <path d="M6 160V64L100 16l94 48v96"/>
      <path d="M44 96h14v20H44zM142 96h14v20h-14z" stroke-width="1.1" opacity=".65"/>
      <path d="M88 134h24v26H88z" stroke-width="1.2"/>
    </g>
    <g id="h-lijst">
      <path d="M6 160V56h188v104"/>
      <path d="M0 56h200M0 50h200" stroke-width="1"/>
      <path d="M52 88h14v22H52zM134 88h14v22h-14z" stroke-width="1.1" opacity=".65"/>
      <path d="M86 132h28v28H86z" stroke-width="1.2"/>
    </g>
    <g id="h-hals">
      <path d="M6 160V66h18V54h16V42h22V24h76v18h22v12h16v12h18v94"/>
      <path d="M60 96h14v18H60zM126 96h14v18h-14z" stroke-width="1.1" opacity=".65"/>
      <path d="M88 134h22v26H88z" stroke-width="1.2"/>
    </g>
  </defs>
  <g>
    <use href="#h-trap" x="0"/>
    <use href="#h-klok" x="200"/>
    <use href="#h-hals" x="400"/>
    <use href="#h-tuit" x="600"/>
    <use href="#h-lijst" x="800"/>
    <use href="#h-klok" x="1000"/>
    <use href="#h-trap" x="1200"/>
    <use href="#h-hals" x="1400"/>
  </g>
  <path d="M0 160h1600" stroke-width="1" opacity=".55"/>
</svg>`;

  function hero() {
    const current = WH.router.current();
    let mode = current.name === "semantic" ? "semantic" : "lookup";
    let value = current.query.q || "";
    const region = el("div");
    let pendingFocus = false;

    function paint() {
      const search = ui.search({
        mode,
        value,
        onModeChange: (next, v) => {
          mode = next;
          value = v;
          pendingFocus = true;
          paint();
        },
        onSubmit: (nextMode, q) => {
          WH.store.addRecent(q, nextMode);
          WH.router.go(nextMode, {}, { q });
        },
      });
      WH.app.registerHomeSearch(search);
      region.replaceChildren(search, sampleRow());
      search.input.value = value;
      if (pendingFocus) {
        pendingFocus = false;
        search.focus();
      }
    }

    function sampleRow() {
      const samples = mode === "semantic" ? SEMANTIC_SAMPLES : LOOKUP_SAMPLES;
      return el(
        "div.sample-chips",
        null,
        el("span.label", null, mode === "semantic" ? "示例" : "试试"),
        samples.map((sample) =>
          el(
            "button.chip",
            {
              attrs: { type: "button", title: sample.q },
              onClick: () => {
                WH.store.addRecent(sample.q, mode);
                WH.router.go(mode, {}, { q: sample.q });
              },
            },
            sample.tag ? el("small", null, sample.tag) : null,
            sample.label,
            sample.hint ? el("small", null, sample.hint) : null
          )
        )
      );
    }

    paint();

    return el(
      "section.hero",
      null,
      el(
        "div.wrap",
        null,
        el(
          "div.hero__grid",
          null,
          el(
            "div",
            null,
            el(
              "div.hero__kicker",
              null,
              el("span.flag", null, el("i"), el("i"), el("i")),
              el("span.eyebrow", null, "Nederlands woordenboek · 荷兰语词典"),
              el("span.eyebrow.edition", { style: "color:var(--rood)" }, "v1")
            ),
            el("h1.display", null, "一个词，", el("br"), el("em", null, "不止一间屋子")),
            el("p.hero__nl", null, "Elk woord heeft meer dan één kamer."),
            region
          ),
          el(
            "aside.hero__aside",
            null,
            el(
              "div.specimen",
              null,
              el(
                "div.specimen__top",
                null,
                el("span.specimen__word", null, WH.withDigraph("huis")),
                el(
                  "span",
                  { style: "display:flex;gap:6px;align-items:center" },
                  ui.levelTicket(1),
                  el("span.mono", { style: "font-size:10px;color:var(--ink-3)" }, "138")
                )
              ),
              el(
                "div.specimen__senses",
                null,
                SPECIMEN.map((s, i) =>
                  el(
                    "div.specimen__sense",
                    { attrs: { title: "源义项编号 " + s.no } },
                    el("span.i", null, String(i + 1).padStart(2, "0")),
                    el("span.nl", null, s.nl),
                    el("span.zh", null, s.zh)
                  )
                )
              ),
              el(
                "div.specimen__foot",
                null,
                el("span", null, WH.api.mode === "http" ? "词条样张 · 2026-10-23 快照" : "13 义项 · 34 词形"),
                el("span", { style: "color:var(--kobalt)" }, "entries/138")
              )
            )
          )
        )
      ),
      el("div.skyline", { html: SKYLINE })
    );
  }

  function tileWall() {
    return el(
      "section.section",
      null,
      el(
        "div.wrap",
        null,
        el(
          "div.section-head",
          null,
          el("h2", null, "词条"),
          el("span.eyebrow", null, WH.api.mode === "http" ? "10 个精选 · 计数为 10-23 快照" : "10 个 · 均可打开")
        ),
        el(
          "div.tegel-grid.tegel-grid--five",
          { dataset: { stagger: "1" } },
          TILES.map((t, i) =>
            el(
              "a.tegel",
              {
                href: WH.router.build("entry", { id: t.id }),
                style: `--i:${i}`,
                attrs: { "aria-label": `${t.lemma}，${t.senses} 个义项，分级 ${t.level}` },
              },
              el("span.tegel__lvl", null, "L" + t.level),
              el("span.tegel__orn", { attrs: { "aria-hidden": "true" } }, WH.icon("medallion", { size: 26 })),
              el("span.tegel__word", null, WH.withDigraph(t.lemma)),
              el(
                "span.tegel__gloss",
                null,
                el("span.tile-count", null, `${t.senses} 义项 · ${t.forms} 词形`),
                el("span.tile-def", null, t.def)
              )
            )
          )
        )
      )
    );
  }

  function taalBand() {
    const facts = [
      ["IJ 是一个字母", "词首两字母一起大写", "IJsselmeer · ijs"],
      ["de 还是 het", "没收录就留空", "de fiets · het huis"],
      ["可分动词", "前缀跑到句尾", "afzetten → zet af"],
    ];
    return el(
      "section.taal-band",
      null,
      el(
        "div.wrap.taal-band__inner",
        null,
        el("div.ij-mark", { attrs: { "aria-hidden": "true" } }, "IJ"),
        el(
          "div",
          null,
          el("span.eyebrow.eyebrow--kobalt", null, "Taalwijzer"),
          el(
            "h2",
            { style: "font-family:var(--font-display);font-size:var(--fs-h2);margin:8px 0 20px;font-weight:380" },
            "荷兰语的六条规矩"
          ),
          el(
            "div.taal-band__facts",
            null,
            facts.map(([title, line, ex]) =>
              el(
                "div.fact",
                null,
                el("h4", null, title),
                el("p", null, line, el("span.nl-ex", null, ex))
              )
            )
          ),
          el(
            "div",
            { style: "margin-top:22px;display:flex;gap:10px;flex-wrap:wrap" },
            el(
              "button.btn.btn--primary",
              { attrs: { type: "button" }, onClick: () => ui.openGuide() },
              "全部六条",
              icon("arrowUpRight", { size: 14 })
            ),
            el("a.btn.btn--ghost", { href: WH.router.build("entry", { id: 2327 }) }, "afzetten · 33 义项")
          )
        )
      )
    );
  }

  function notes() {
    const items = [
      ["score", "排序分，不是准确率"],
      ["corpus", "语料例句未消歧"],
      WH.api.mode === "http" ? ["live", "已连接本机真实词库"] : ["offline", "回放 69 条响应"],
    ];
    return el(
      "section.section--tight",
      null,
      el(
        "div.wrap",
        null,
        el(
          "div.notes-strip",
          null,
          items.map(([key, text]) =>
            el("div.note-item", null, el("span.mono.note-key", null, key), el("span", null, text))
          ),
          el(
            "a.btn.btn--quiet.btn--sm",
            { href: WH.router.build("about") },
            "说明",
            icon("arrowRight", { size: 13 })
          )
        )
      )
    );
  }

  function recentStrip() {
    const recent = WH.store.state.recent;
    if (!recent.length) return null;
    return el(
      "div.wrap",
      { style: "padding-top:26px" },
      el(
        "div",
        { style: "display:flex;flex-wrap:wrap;gap:8px;align-items:center" },
        el("span.label", null, "最近"),
        recent.map((r) =>
          el(
            "button.chip",
            {
              attrs: { type: "button" },
              onClick: () => WH.router.go(r.mode === "semantic" ? "semantic" : "lookup", {}, { q: r.q }),
            },
            r.mode === "semantic" ? "意 · " : "",
            r.q
          )
        ),
        el(
          "button.link-btn",
          {
            attrs: { type: "button" },
            onClick: () => {
              WH.store.clearRecent();
              WH.app.render();
            },
          },
          "清空"
        )
      )
    );
  }

  WH.views = WH.views || {};
  WH.views.home = function () {
    return el("div", null, hero(), recentStrip(), tileWall(), taalBand(), notes());
  };
})();
