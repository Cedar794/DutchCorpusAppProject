/* ==========================================================================
   Woordhuis · saved words  (local only; nothing leaves the browser)
   ========================================================================== */
(function () {
  "use strict";

  const WH = (window.WH = window.WH || {});
  const { el, icon } = WH;
  const ui = WH.ui;

  WH.views = WH.views || {};

  WH.views.saved = function () {
    const wrap = el("div.wrap");
    const saved = WH.store.state.saved;

    wrap.appendChild(
      el(
        "div.results-head",
        null,
        el("span.mode-note", null, "WOORDENSCHAT · 我的词库"),
        el(
          "h1.query-quote",
          { style: "margin-top:14px;font-size:clamp(1.8rem,3.6vw,2.6rem)" },
          "收起来的词"
        ),
        el("p.panel__count", { style: "margin-top:8px" }, "localStorage · 无账号 · 无同步")
      )
    );

    if (!saved.length) {
      wrap.appendChild(
        ui.state({
          code: "LEEG · 空",
          title: "词库是空的",
          text: "在词条右上角点「收进词库」。",
          actions: [
            el("a.btn.btn--primary", { href: WH.router.build("home") }, "去查一个词"),
            el(
              "a.btn.btn--ghost",
              { href: WH.router.build("entry", { id: 138 }) },
              "先看看 huis"
            ),
          ],
          iconName: "bookmark",
        })
      );
      return wrap;
    }

    const list = el("div.saved-list");
    list.appendChild(
      el(
        "div",
        { style: "display:flex;justify-content:space-between;align-items:baseline;padding:12px 0" },
        el("span.eyebrow", null, saved.length + " 个词"),
        el(
          "button.link-btn",
          {
            attrs: { type: "button" },
            onClick: () => {
              WH.store.clearSaved();
              WH.toast("词库已清空");
              WH.app.render();
            },
          },
          "清空"
        )
      )
    );

    for (const item of saved) {
      list.appendChild(
        el(
          "div.saved-row",
          null,
          el(
            "div.saved-row__main",
            null,
            el(
              "a.saved-row__word",
              { href: WH.router.build("entry", { id: item.lemma_id }) },
              WH.withDigraph(item.lemma)
            ),
            ui.levelTicket(item.level),
            item.gloss
              ? el("span.saved-row__gloss", null, item.gloss)
              : el("span.saved-row__gloss", null, "（没有第一义项译文）")
          ),
          el(
            "div",
            { style: "display:flex;gap:8px;align-items:center" },
            el(
              "button.icon-btn",
              {
                attrs: { type: "button", "aria-label": "从词库移除 " + item.lemma, title: "移除" },
                onClick: () => {
                  WH.store.toggleSave({ lemma_id: item.lemma_id });
                  WH.app.render();
                },
              },
              icon("close", { size: 15 })
            )
          )
        )
      );
    }

    wrap.appendChild(list);
    wrap.appendChild(
      el(
        "div",
        { style: "margin-top:26px;display:flex;gap:10px;flex-wrap:wrap" },
        el("a.btn.btn--ghost", { href: WH.router.build("home") }, "继续查词"),
        el("a.btn.btn--quiet", { href: WH.router.build("about") }, "这些数据存在哪")
      )
    );
    return wrap;
  };
})();
