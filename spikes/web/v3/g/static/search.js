// Mock-up round 3: search over a small JSON index ([kind, text, extra, url] per entry), in
// the browser, with no outside service. Header box: up to 6 suggestions; Enter or «see all»
// opens the search page, which lists every match.
// Matching copied and adapted from Paleo Atlas (site/static/search.js, same author, AGPL):
// accents and case ignored, plurals stripped, prefixes matched, small typos tolerated.
(function () {
  "use strict";
  var STOP = new Set(["de", "del", "la", "las", "el", "los", "en", "y", "the", "of", "and", "in", "a"]);
  function norm(s) {
    return String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
      .replace(/[^a-z0-9]+/g, " ").trim();
  }
  function stem(w) {
    if (w.length > 5 && /[^aeiou]es$/.test(w)) return w.slice(0, -2);
    if (w.length > 3 && w.endsWith("s") && !w.endsWith("us") && !w.endsWith("is")) return w.slice(0, -1);
    return w;
  }
  function words(s) {
    return norm(s).split(" ").filter(function (w) { return w.length > 1 && !STOP.has(w); }).map(stem);
  }
  function lev(a, b, max) {
    if (Math.abs(a.length - b.length) > max) return max + 1;
    var prev = [], cur, i, j;
    for (j = 0; j <= b.length; j++) prev[j] = j;
    for (i = 1; i <= a.length; i++) {
      cur = [i];
      var best = i;
      for (j = 1; j <= b.length; j++) {
        cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
        if (cur[j] < best) best = cur[j];
      }
      if (best > max) return max + 1;
      prev = cur;
    }
    return prev[b.length];
  }
  function quality(q, t) {
    if (t === q) return 1;
    if (t.startsWith(q)) return q.length >= 2 ? 0.8 : 0;
    if (q.length < 4 || q[0] !== t[0]) return 0;
    var max = q.length >= 8 ? 2 : 1;
    var d = Math.min(lev(q, t, max), lev(q, t.slice(0, q.length), max));
    return d <= max ? 0.5 : 0;
  }
  // Every query word must match some word; the text counts double the extra words.
  function score(qw, e) {
    var total = 0;
    for (var i = 0; i < qw.length; i++) {
      var best = 0;
      e.tw.forEach(function (t) { best = Math.max(best, 2 * quality(qw[i], t)); });
      e.xw.forEach(function (t) { best = Math.max(best, quality(qw[i], t)); });
      if (!best) return 0;
      total += best;
    }
    return total;
  }
  var cache = {};
  function load(src) {
    if (!cache[src]) cache[src] = fetch(src).then(function (r) { return r.json(); }).then(function (rows) {
      return rows.map(function (r) { return { kind: r[0], text: r[1], url: r[3], tw: words(r[1]), xw: words(r[2]) }; });
    });
    return cache[src];
  }
  function find(entries, q) {
    var qw = words(q);
    if (!qw.length) return [];
    return entries.map(function (e) { return [score(qw, e), e]; })
      .filter(function (x) { return x[0] > 0; })
      .sort(function (a, b) { return b[0] - a[0]; })
      .map(function (x) { return x[1]; });
  }
  function href(base, u) { return !u || /^https?:/.test(u) ? u : base + u; }
  function item(base, e, tag) {
    var li = document.createElement(tag || "li");
    var a = document.createElement(e.url ? "a" : "span");
    if (e.url) {
      a.href = href(base, e.url);
      if (/^https?:/.test(e.url)) { a.rel = "noopener"; a.target = "_blank"; }
    }
    var k = document.createElement("span"); k.className = "kind"; k.textContent = e.kind;
    a.appendChild(k); a.appendChild(document.createTextNode(" " + e.text));
    li.appendChild(a);
    return li;
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-search]").forEach(function (form) {
      var input = form.querySelector("input"), list = form.querySelector(".suggest");
      var base = form.getAttribute("data-base"), timer = null;
      function close() { list.hidden = true; input.setAttribute("aria-expanded", "false"); }
      input.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          var q = input.value.trim();
          if (q.length < 2) { close(); return; }
          load(form.getAttribute("data-index")).then(function (entries) {
            var hits = find(entries, q);
            list.textContent = "";
            if (!hits.length) {
              var li = document.createElement("li"); li.className = "none";
              li.textContent = form.getAttribute("data-none").replace("{q}", q);
              list.appendChild(li);
            }
            hits.slice(0, 6).forEach(function (e) { list.appendChild(item(base, e)); });
            if (hits.length > 6) {
              var all = document.createElement("li"), a = document.createElement("a");
              a.href = form.action + "?q=" + encodeURIComponent(q);
              a.textContent = form.getAttribute("data-all") + " (" + hits.length + ")";
              all.className = "all"; all.appendChild(a); list.appendChild(all);
            }
            list.hidden = false; input.setAttribute("aria-expanded", "true");
          });
        }, 120);
      });
      input.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
      document.addEventListener("click", function (e) { if (!form.contains(e.target)) close(); });
    });

    var page = document.querySelector("[data-search-page]");
    if (!page) return;
    var q = new URLSearchParams(location.search).get("q") || "";
    var form = document.querySelector("[data-search]");
    if (form) form.querySelector("input").value = q;
    var status = page.querySelector(".search-status"), out = page.querySelector(".results");
    if (q.trim().length < 2) return;
    load(form.getAttribute("data-index")).then(function (entries) {
      var hits = find(entries, q);
      status.textContent = hits.length ? page.getAttribute("data-n").replace("{n}", hits.length).replace("{q}", q)
                                       : page.getAttribute("data-none").replace("{q}", q);
      hits.forEach(function (e) { out.appendChild(item(form.getAttribute("data-base"), e)); });
    });
  });
})();
