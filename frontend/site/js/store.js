/* ==========================================================================
   Woordhuis · store
   Preferences, saved words, recent searches. Persisted in localStorage only.
   ========================================================================== */
(function () {
  "use strict";

  const WH = (window.WH = window.WH || {});
  const { storage } = WH;

  const listeners = new Set();

  const state = {
    prefs: Object.assign(
      { glossLang: "zh", theme: "dag" },
      storage.get("prefs", {})
    ),
    saved: storage.get("saved", []),
    recent: storage.get("recent", []),
  };

  function emit() {
    for (const fn of listeners) fn(state);
  }

  function persist() {
    storage.set("prefs", state.prefs);
    storage.set("saved", state.saved);
    storage.set("recent", state.recent);
  }

  function applyDocumentPrefs() {
    const root = document.documentElement;
    root.dataset.theme = state.prefs.theme;
    root.dataset.gloss = state.prefs.glossLang;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", state.prefs.theme === "nacht" ? "#0d1622" : "#f7f5ef");
  }

  const store = {
    state,

    init() {
      applyDocumentPrefs();
    },

    on(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },

    setPref(key, value) {
      state.prefs[key] = value;
      applyDocumentPrefs();
      persist();
      emit();
    },

    toggleTheme() {
      store.setPref("theme", state.prefs.theme === "nacht" ? "dag" : "nacht");
    },

    setGlossLang(lang) {
      store.setPref("glossLang", lang);
    },

    isSaved(lemmaId) {
      return state.saved.some((s) => Number(s.lemma_id) === Number(lemmaId));
    },

    toggleSave(item) {
      const id = Number(item.lemma_id);
      const at = state.saved.findIndex((s) => Number(s.lemma_id) === id);
      if (at >= 0) {
        state.saved.splice(at, 1);
        persist();
        emit();
        return false;
      }
      state.saved.unshift({
        lemma_id: id,
        lemma: item.lemma,
        gloss: item.gloss || "",
        level: item.level || null,
        at: Date.now(),
      });
      state.saved = state.saved.slice(0, 120);
      persist();
      emit();
      return true;
    },

    addRecent(query, mode) {
      const q = String(query || "").trim();
      if (!q) return;
      state.recent = [
        { q, mode, at: Date.now() },
        ...state.recent.filter((r) => r.q !== q || r.mode !== mode),
      ].slice(0, 6);
      persist();
      emit();
    },

    clearSaved() {
      state.saved = [];
      persist();
      emit();
    },

    clearRecent() {
      state.recent = [];
      persist();
      emit();
    },
  };

  WH.store = store;
})();
