// Mock-ups round 2: theme, tabs, type filters and «show more». Plain JS, no framework.
// Without JS every panel and every item stays visible.
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
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-theme-toggle]");
    if (!b) return;
    var next = { auto: "light", light: "dark", dark: "auto" }[read()];
    save(next); apply(next);
  });

  document.addEventListener("DOMContentLoaded", function () {
    apply(read());
    // Lists: [data-page] shows N items, the button [data-more] the next N; filters reset it.
    var lists = {};
    document.querySelectorAll("[data-page]").forEach(function (list) {
      var st = { list: list, size: +list.getAttribute("data-page"), shown: 0, filter: "all",
                 btn: document.querySelector('[data-more="' + list.id + '"]'),
                 empty: list.parentNode.querySelector("[data-filter-empty]") };
      st.shown = st.size;
      lists[list.id] = st;
      if (st.btn) st.btn.addEventListener("click", function () { st.shown += st.size; draw(st); });
      draw(st);
    });
    function draw(st) {
      var match = 0, visible = 0;
      st.list.querySelectorAll("[data-type]").forEach(function (item) {
        var ok = st.filter === "all" || item.getAttribute("data-type") === st.filter;
        if (ok) match++;
        item.hidden = !ok || match > st.shown;
        if (!item.hidden) visible++;
      });
      if (st.btn) {
        st.btn.hidden = match <= st.shown;
        st.btn.textContent = st.btn.textContent.replace(/ \(\d+\)$/, "") + " (" + (match - visible) + ")";
      }
      if (st.empty) st.empty.hidden = match > 0;
    }
    document.querySelectorAll("[data-filters]").forEach(function (bar) {
      var st = lists[bar.getAttribute("data-filters")];
      if (!st) return;
      bar.addEventListener("click", function (e) {
        var b = e.target.closest("[data-filter]");
        if (!b) return;
        bar.querySelectorAll("[data-filter]").forEach(function (x) {
          x.setAttribute("aria-pressed", String(x === b));
        });
        st.filter = b.getAttribute("data-filter");
        st.shown = st.size;
        draw(st);
      });
    });

    // Tabs (WAI-ARIA pattern: arrows move, Home/End jump); the hash keeps the open tab.
    document.querySelectorAll("[data-tabs]").forEach(function (box) {
      var tabs = Array.prototype.slice.call(box.querySelectorAll('[role="tab"]'));
      function select(tab, focus, push) {
        tabs.forEach(function (t) {
          var on = t === tab;
          t.setAttribute("aria-selected", String(on));
          t.tabIndex = on ? 0 : -1;
          document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
        });
        if (focus) tab.focus();
        if (push) { try { history.replaceState(null, "", "#" + tab.id); } catch (e) { /* file:// */ } }
      }
      box.addEventListener("click", function (e) {
        var t = e.target.closest('[role="tab"]');
        if (t) select(t, false, true);
      });
      box.addEventListener("keydown", function (e) {
        var i = tabs.indexOf(document.activeElement);
        if (i < 0) return;
        var j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
        if (j === undefined) return;
        e.preventDefault();
        select(tabs[(j + tabs.length) % tabs.length], true, true);
      });
      var start = location.hash && document.getElementById(location.hash.slice(1));
      select(start && tabs.indexOf(start) >= 0 ? start : tabs[0], false, false);
    });
  });
})();

// Round 3: the topics carousel. Buttons scroll one card; touch and trackpad scroll natively.
document.addEventListener("click", function (e) {
  var b = e.target.closest("[data-scroll]");
  if (!b) return;
  var rail = document.getElementById(b.getAttribute("aria-controls"));
  var card = rail && rail.querySelector("li");
  if (card) rail.scrollBy({ left: +b.getAttribute("data-scroll") * (card.offsetWidth + 12), behavior: "smooth" });
});
