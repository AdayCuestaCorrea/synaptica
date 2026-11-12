// Tabs for mock-up B (WAI-ARIA tabs pattern: arrows move, Home/End jump). The hash keeps
// the open tab, so a link like index.html#tab-nsc opens «Nature · Science · Cell».
(function () {
  "use strict";
  document.querySelectorAll("[data-tabs]").forEach(function (box) {
    var tabs = Array.prototype.slice.call(box.querySelectorAll('[role="tab"]'));
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      });
      if (focus) tab.focus();
      try { history.replaceState(null, "", "#" + tab.id); } catch (e) { /* file:// */ }
    }
    box.addEventListener("click", function (e) {
      var t = e.target.closest('[role="tab"]');
      if (t) select(t, false);
    });
    box.addEventListener("keydown", function (e) {
      var i = tabs.indexOf(document.activeElement);
      if (i < 0) return;
      var j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
      if (j === undefined) return;
      e.preventDefault();
      select(tabs[(j + tabs.length) % tabs.length], true);
    });
    var start = location.hash && document.getElementById(location.hash.slice(1));
    if (start && tabs.indexOf(start) >= 0) select(start, false);
  });
})();
