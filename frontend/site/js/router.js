/* ==========================================================================
   Woordhuis · router
   Hash routes keep the package openable straight from the file system.
     #/                         home
     #/zoeken?q=huizen          ordinary lookup result
     #/betekenis?q=…            meaning search (POST on demand, cached)
     #/woord/138?…              entry
     #/woordenschat             saved words
     #/over                     about / data
   ========================================================================== */
(function () {
  "use strict";

  const WH = (window.WH = window.WH || {});

  const ROUTES = [
    { name: "home", re: /^\/?$/ },
    { name: "lookup", re: /^\/zoeken\/?$/ },
    { name: "semantic", re: /^\/betekenis\/?$/ },
    { name: "entry", re: /^\/woord\/(\d+)\/?$/, keys: ["id"] },
    { name: "saved", re: /^\/woordenschat\/?$/ },
    { name: "about", re: /^\/over\/?$/ },
  ];

  function parse(hash) {
    const raw = (hash || "").replace(/^#/, "") || "/";
    const qIndex = raw.indexOf("?");
    const path = qIndex >= 0 ? raw.slice(0, qIndex) : raw;
    const search = qIndex >= 0 ? raw.slice(qIndex + 1) : "";
    const query = {};
    for (const [k, v] of new URLSearchParams(search)) query[k] = v;
    for (const route of ROUTES) {
      const m = route.re.exec(path);
      if (!m) continue;
      const params = {};
      (route.keys || []).forEach((key, i) => {
        params[key] = m[i + 1];
      });
      return { name: route.name, params, query, path };
    }
    return { name: "notfound", params: {}, query, path };
  }

  function build(name, params = {}, query = {}) {
    const search = new URLSearchParams(
      Object.entries(query).filter(([, v]) => v !== undefined && v !== null && v !== "")
    ).toString();
    const base = {
      home: "/",
      lookup: "/zoeken",
      semantic: "/betekenis",
      entry: "/woord/" + (params.id || ""),
      saved: "/woordenschat",
      about: "/over",
    }[name];
    return "#" + (base || "/") + (search ? "?" + search : "");
  }

  function go(name, params, query, { replace = false } = {}) {
    const href = build(name, params, query);
    if (location.hash === href) {
      WH.app && WH.app.render && WH.app.render();
      return;
    }
    if (replace) {
      const url = location.pathname + location.search + href;
      history.replaceState(null, "", url);
      WH.app && WH.app.render && WH.app.render();
    } else {
      location.hash = href;
    }
  }

  const router = {
    parse,
    build,
    go,
    current() {
      return parse(location.hash);
    },
    start(onRoute) {
      window.addEventListener("hashchange", () => onRoute(parse(location.hash)));
      onRoute(parse(location.hash));
    },
  };

  WH.router = router;
})();
