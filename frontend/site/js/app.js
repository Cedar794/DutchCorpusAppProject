/* ==========================================================================
   Woordhuis · app shell
   ========================================================================== */
(function () {
  "use strict";

  const WH = (window.WH = window.WH || {});
  const { el } = WH;

  const TITLES = {
    home: "woordhuis · 荷兰语词典",
    lookup: (r) => (r.query.q ? "「" + r.query.q + "」· 查词" : "查词") + " — woordhuis",
    semantic: (r) => (r.query.q ? "「" + r.query.q + "」· 按意思找词" : "按意思找词") + " — woordhuis",
    entry: () => "词条 — woordhuis",
    saved: "我的词库 — woordhuis",
    about: "数据与方法 — woordhuis",
    notfound: "找不到页面 — woordhuis",
  };

  let cleanup = null;
  let homeSearch = null;
  let mountedSomething = false;
  let firstRender = true;

  function setTitle(route) {
    const value = TITLES[route.name];
    document.title = typeof value === "function" ? value(route) : value || "woordhuis";
  }

  function notFound(route, mount) {
    const node = WH.ui.state({
      code: "404 · 页面",
      title: "这个地址没有对应的页面",
      text: "链接可能过期了，或者手写的路由有笔误。查词入口在首页。",
      actions: [el("a.btn.btn--primary", { href: WH.router.build("home") }, "回到首页")],
      iconName: "windmill",
    });
    return el("div.wrap", null, node);
  }

  const VIEWS = {
    home: (route, mount) => WH.views.home(route, mount),
    lookup: (route, mount) => WH.views.lookup(route, mount),
    semantic: (route, mount) => WH.views.semantic(route, mount),
    entry: (route, mount) => WH.views.entry(route, mount),
    saved: (route, mount) => WH.views.saved(route, mount),
    about: (route, mount) => WH.views.about(route, mount),
    notfound: (route, mount) => notFound(route, mount),
  };

  function render() {
    const route = WH.router.current();
    const main = document.getElementById("main");
    if (!main) return;

    if (typeof cleanup === "function") {
      try {
        cleanup();
      } catch (e) {
        /* a view cleanup must never break navigation */
      }
    }
    cleanup = null;
    mountedSomething = false;

    document.getElementById("app-header").replaceChildren(WH.ui.header());

    const mount = (node) => {
      mountedSomething = true;
      main.replaceChildren(node);
    };

    let result;
    try {
      result = (VIEWS[route.name] || VIEWS.notfound)(route, mount);
    } catch (err) {
      console.error(err);
      result = WH.ui.state({
        code: "界面错误",
        title: "这个视图没能渲染出来",
        text: String((err && err.message) || err),
        actions: [el("a.btn.btn--primary", { href: WH.router.build("home") }, "回到首页")],
      });
    }

    if (typeof result === "function") cleanup = result;
    else if (result instanceof Node && !mountedSomething) main.replaceChildren(result);

    if (WH.motion) WH.motion.enter(main);

    setTitle(route);
    document.documentElement.dataset.route = route.name;

    const keepScroll = Boolean(route.query.to);
    if (!keepScroll) {
      window.scrollTo({ top: 0, behavior: firstRender ? "auto" : "instant" });
    }
    if (!firstRender) {
      // move focus for screen readers without stealing it from the search box
      main.setAttribute("tabindex", "-1");
      main.focus({ preventScroll: true });
    }
    firstRender = false;
  }

  /* --------------------------------------------------------------- actions -- */

  WH.app = {
    render,
    registerHomeSearch(search) {
      homeSearch = search;
    },
    focusSearch() {
      const route = WH.router.current();
      if (route.name === "home" && homeSearch) {
        homeSearch.focus();
        return;
      }
      WH.router.go("home");
      setTimeout(() => {
        if (homeSearch) homeSearch.focus();
      }, 60);
    },
    playScenario(scenario) {
      if (!scenario) return;
      WH.api.forceScenario(scenario.id);
      if (WH.cache && WH.cache.clearSemantic) WH.cache.clearSemantic();
      WH.toast("强制回放：" + scenario.id + "（" + scenario.status + "）");
      const q = (scenario.json && scenario.json.query) || (scenario.query && scenario.query.q) || "";
      if (scenario.path === "/semantic-search") {
        WH.router.go("semantic", {}, { q: q || "回放场景" });
      } else if (scenario.path.startsWith("/entries/")) {
        const id = scenario.path.split("/")[2];
        WH.router.go("entry", { id }, {});
      } else if (scenario.path.startsWith("/senses/")) {
        const id = scenario.path.split("/")[2];
        WH.router.go("entry", { id: 662 }, { to: "betekenissen" });
      } else {
        WH.router.go("lookup", {}, { q: q || "huis" });
      }
      setTimeout(() => render(), 30);
    },
  };

  /* ------------------------------------------------------------------ boot -- */

  function boot() {
    WH.store.init();
    WH.api.init();

    document.getElementById("app-footer").appendChild(WH.ui.footer());

    const params = new URLSearchParams(location.search);
    if (WH.api.mode === "demo" && params.get("inspector") !== "0" && window.innerWidth > 760) {
      document.getElementById("app-inspector").appendChild(WH.ui.inspector());
    }

    WH.store.on(() => {
      if (WH.router.current().name === "saved") render();
    });

    document.addEventListener("keydown", (event) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) ||
        document.activeElement.isContentEditable;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        WH.app.focusSearch();
      } else if (event.key === "/" && !typing) {
        event.preventDefault();
        WH.app.focusSearch();
      } else if (event.key === "Escape") {
        const dialog = document.querySelector("dialog.sheet[open]");
        if (dialog) dialog.close();
      }
    });

    WH.router.start(() => render());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
