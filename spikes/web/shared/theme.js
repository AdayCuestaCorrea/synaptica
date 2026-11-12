// Theme (auto / light / dark) and type filters, shared by the three mock-ups. No framework.
// The choice is a per-viewer convenience: localStorage, wrapped in try/catch.
(function () {
  "use strict";
  var KEY = "synaptica-theme";
  var root = document.documentElement;
  function read() { try { return localStorage.getItem(KEY) || "auto"; } catch (e) { return "auto"; } }
  function save(v) { try { localStorage.setItem(KEY, v); } catch (e) { /* private mode */ } }
  function apply(v) {
    if (v === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", v);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
      var label = b.querySelector("[data-theme-label]");
      if (label) label.textContent = b.getAttribute("data-l-" + v);
    });
  }
  apply(read()); // runs in <head>: no flash of the wrong theme
  document.addEventListener("DOMContentLoaded", function () { apply(read()); initFilters(); });
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-theme-toggle]");
    if (!b) return;
    var next = { auto: "light", light: "dark", dark: "auto" }[read()];
    save(next); apply(next);
  });

  // Filters: buttons [data-filter] with aria-pressed; items [data-type] in the target list.
  function initFilters() { document.querySelectorAll("[data-filters]").forEach(function (bar) {
    var list = document.getElementById(bar.getAttribute("data-filters"));
    if (!list) return;
    var empty = (list.closest("section") || list.parentNode).querySelector("[data-filter-empty]");
    bar.addEventListener("click", function (e) {
      var b = e.target.closest("[data-filter]");
      if (!b) return;
      var f = b.getAttribute("data-filter");
      bar.querySelectorAll("[data-filter]").forEach(function (x) {
        x.setAttribute("aria-pressed", String(x === b));
      });
      var shown = 0;
      list.querySelectorAll("[data-type]").forEach(function (item) {
        var ok = f === "all" || item.getAttribute("data-type") === f;
        item.hidden = !ok;
        if (ok) shown++;
      });
      if (empty) empty.hidden = shown > 0;
    });
  }); }
})();
