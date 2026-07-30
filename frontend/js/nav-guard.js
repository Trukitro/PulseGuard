/** Blocks external navigation/window.open by default so a stray <a> or script
 * can never hand off to the user's real default browser inside the pywebview
 * shell. Only an explicit `data-external-ok` link is allowed through, and even
 * then it's routed to Python's webbrowser.open() via the pywebview js_api
 * bridge -- never opened in-place. In a plain dev-mode browser tab (no
 * pywebview bridge present) such links are just quietly ignored. */
(function installNavGuard() {
  function isSameOrigin(url) {
    try {
      return new URL(url, location.href).origin === location.origin;
    } catch {
      return false;
    }
  }

  function routeExternal(url) {
    if (window.pywebview?.api?.open_external) {
      window.pywebview.api.open_external(url);
    } else {
      console.warn("[nav-guard] blocked external navigation (no pywebview bridge):", url);
    }
  }

  document.addEventListener(
    "click",
    (event) => {
      const anchor = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!anchor) return;

      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("#")) return;
      if (isSameOrigin(href)) return;

      event.preventDefault();
      if (anchor.hasAttribute("data-external-ok")) {
        routeExternal(anchor.href);
      } else {
        console.warn("[nav-guard] blocked external link:", href);
      }
    },
    true
  );

  const nativeOpen = window.open.bind(window);
  window.open = function guardedOpen(url, ...rest) {
    if (url && !isSameOrigin(url)) {
      console.warn("[nav-guard] blocked window.open:", url);
      return null;
    }
    return nativeOpen(url, ...rest);
  };
})();
