/* ==========================================================================
   Woordhuis · motion helpers
   Page enter, theme wipe, loading labels. All of it is opt-out.
   ========================================================================== */
(function () {
  "use strict";

  const WH = (window.WH = window.WH || {});

  const reduced = () =>
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let enterTimer = 0;

  const motion = {
    reduced,

    /** re-trigger the route-enter animation on the main column */
    enter(main) {
      if (!main || reduced()) return;
      main.classList.remove("is-entering");
      // eslint-disable-next-line no-unused-expressions
      void main.offsetWidth;
      main.classList.add("is-entering");
      clearTimeout(enterTimer);
      enterTimer = setTimeout(() => main.classList.remove("is-entering"), 620);
    },

    /** theme switch, radial from the button when view transitions exist */
    toggleTheme(event) {
      const apply = () => WH.store.toggleTheme();
      if (reduced() || !document.startViewTransition || !event || !event.clientX) {
        apply();
        return;
      }
      const x = event.clientX;
      const y = event.clientY;
      const radius = Math.hypot(
        Math.max(x, window.innerWidth - x),
        Math.max(y, window.innerHeight - y)
      );
      const transition = document.startViewTransition(apply);
      transition.ready
        .then(() => {
          document.documentElement.animate(
            {
              clipPath: [
                `circle(0px at ${x}px ${y}px)`,
                `circle(${radius}px at ${x}px ${y}px)`,
              ],
            },
            {
              duration: 420,
              easing: "cubic-bezier(.22,.61,.36,1)",
              pseudoElement: "::view-transition-new(root)",
            }
          );
        })
        .catch(() => {});
    },

    /** a spinner + label for a button that is fetching */
    spinner(text) {
      return WH.dom.frag(
        WH.el("span.spinner", { attrs: { "aria-hidden": "true" } }),
        WH.el("span", null, text)
      );
    },
  };

  WH.motion = motion;
})();
