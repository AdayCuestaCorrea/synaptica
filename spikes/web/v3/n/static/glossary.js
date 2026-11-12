// Glossary (mock-up). Copied and adapted from Paleo Atlas, site/static/glossary.js (same
// author, AGPL): the taxon previews and the category chips are gone; a term without a
// definition in this language shows «definition pending»; the footer of a popover says the
// definition is a sample still to review instead of citing Wikipedia.
// Progressive enhancement: without JavaScript a marked term is a link to its entry.
//  * a glossary term (a.gl): hover, focus or tap shows its definition. Kept on its term
//    for LOCK_MS (a bar fills up), the popover locks: the pointer can move into it, and
//    a term inside it opens another popover on top, and so on. Leaving a popover closes
//    it and those above it; leaving them all closes everything;
//  * the glossary page: search box.
(function () {
  "use strict";

  // ------------------------------------------------------------ glossary page
  var q = document.getElementById("gl-q");
  if (q) {
    var none = document.querySelector(".gl-none");
    q.hidden = false;
    var fold = function (s) { return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); };
    q.addEventListener("input", function () {
      var v = fold(q.value.trim()), any = false;
      document.querySelectorAll(".gl-entry").forEach(function (e) {
        e.hidden = !!v && fold(e.dataset.q).indexOf(v) < 0;
        any = any || !e.hidden;
      });
      document.querySelectorAll(".gl-letter").forEach(function (s) {
        s.hidden = !s.querySelector(".gl-entry:not([hidden])");
      });
      if (none) { none.hidden = any; none.textContent = none.textContent.replace(/«.*»/, "«" + q.value.trim() + "»"); }
    });
  }

  // ---------------------------------------------------------- popovers (pages)
  var node = document.getElementById("page-data");
  if (!node) return;
  var data = JSON.parse(node.textContent), L = data.labels;
  var LOCK_MS = 1500;
  var touch = window.matchMedia && matchMedia("(hover: none)").matches;
  var stack = [];  // {pop, trigger, locked, timer}

  function el(tag, cls, text) {
    var e = document.createElement(tag); if (cls) e.className = cls;
    if (text) e.textContent = text; return e;
  }
  function place(pop, a) {
    var r = a.getBoundingClientRect(), w = document.documentElement.clientWidth;
    pop.hidden = false;
    pop.style.left = Math.max(8, Math.min(r.left + window.scrollX, window.scrollX + w - pop.offsetWidth - 8)) + "px";
    pop.style.top = (r.bottom + window.scrollY + 6) + "px";
  }
  function termContent(pop, key, written, a) {
    var t = data.glossary[key];
    var head = el("p", "gl-pop__term", t.term);
    if (written && written.toLowerCase() !== t.term.toLowerCase()) {
      head.appendChild(el("span", "gl-pop__also", " · " + L.gl_also + " " + written));
    }
    pop.appendChild(head);
    var def = el("p", "gl-pop__def");
    if (t.pending) { def.textContent = L.gl_pending; def.classList.add("is-pending"); }
    else def.innerHTML = t.html;  // built and escaped by glossary.py
    pop.appendChild(def);
    var foot = el("p", "gl-pop__foot");
    var see = el("a", null, L.gl_see + " →"); see.href = a.getAttribute("href");
    if (!t.pending) foot.append(L.gl_review + " · ");
    foot.append(see);
    pop.appendChild(foot);
  }
  // Close the popovers above ``level`` (all of them with 0).
  function closeFrom(level) {
    while (stack.length > level) {
      var top = stack.pop(); clearTimeout(top.timer); top.pop.remove();
    }
  }
  // Open a popover for ``a`` at ``level`` (0 for a term in the page, n + 1 for a term
  // inside popover n): what was above that level closes.
  function open(a, level, lockNow) {
    if (stack[level] && stack[level].trigger === a) return;
    var key = a.dataset.gl;
    if (!key || !data.glossary[key]) return;
    closeFrom(level);
    var pop = el("div", "gl-pop");
    pop.setAttribute("role", "dialog"); pop.setAttribute("aria-label", data.glossary[key].term);
    pop.dataset.level = level;
    termContent(pop, key, a.textContent, a);
    var bar = el("span", "gl-pop__lock"); pop.appendChild(bar);
    pop.style.zIndex = 30 + level;
    document.body.appendChild(pop);
    var entry = { pop: pop, trigger: a, locked: false, timer: null };
    stack.push(entry);
    place(pop, a);
    var lock = function () { entry.locked = true; pop.classList.add("is-locked"); };
    if (lockNow) lock();  // keyboard and touch need no waiting
    else { pop.classList.add("is-locking"); bar.style.animationDuration = LOCK_MS + "ms"; entry.timer = setTimeout(lock, LOCK_MS); }
  }
  // Where the pointer is decides what stays open: the deepest popover (or its trigger)
  // under it, and everything below that one.
  // A short grace lets the pointer cross the gap between a term and its popover.
  var closeTimer;
  function pointerAt(target) {
    var keep = -1;
    for (var i = 0; i < stack.length; i++) {
      var e = stack[i];
      if (e.trigger.contains(target) || (e.locked && e.pop.contains(target))) keep = i;
    }
    clearTimeout(closeTimer);
    if (stack.length > keep + 1) closeTimer = setTimeout(function () { closeFrom(keep + 1); }, 300);
  }

  if (!touch) {
    document.addEventListener("mouseover", function (e) {
      var a = e.target.closest("a.gl");
      var inPop = e.target.closest(".gl-pop");
      if (a && inPop) {
        var level = +inPop.dataset.level, host = stack[level];
        if (host && host.locked) open(a, level + 1, false);
      } else if (a) {
        open(a, 0, false);
      }
      pointerAt(e.target);
    });
    document.addEventListener("mouseleave", function () { closeFrom(0); });
  }
  document.addEventListener("focusin", function (e) {
    var a = e.target.closest("a.gl");
    if (!a) return;
    var inPop = e.target.closest(".gl-pop");
    open(a, inPop ? +inPop.dataset.level + 1 : 0, true);
  });
  // What made the click: a tap must never follow the term's link, even when the tap
  // already focused it and "focusin" opened the popover (Chrome on Android). Only the
  // popover's own "see in the glossary" link navigates. A mouse click still does.
  var lastPointer = "";
  document.addEventListener("pointerdown", function (e) { lastPointer = e.pointerType || ""; }, true);
  document.addEventListener("click", function (e) {
    var g = e.target.closest("a.gl");
    var inPop = e.target.closest(".gl-pop");
    var tapped = lastPointer === "touch" || lastPointer === "pen" || (!lastPointer && touch);
    if (tapped && g) {  // a tap opens the definition (inside a popover, one more on top)
      e.preventDefault();
      var level = inPop ? +inPop.dataset.level + 1 : 0;
      if (!(stack[level] && stack[level].trigger === g)) open(g, level, true);
      return;
    }
    if (!inPop && !g) closeFrom(0);
  });
  document.addEventListener("keydown", function (e) { lastPointer = "key"; if (e.key === "Escape") closeFrom(stack.length - 1); });
  // Coming back to the page from the glossary: no popover left open.
  window.addEventListener("pageshow", function (e) { if (e.persisted) closeFrom(0); });
})();
