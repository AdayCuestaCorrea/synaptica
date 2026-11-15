// Neuro Atlas page (SCOPE v161): filter the region lists as you type. No library, no network.
// Without JavaScript the lists are still there, folded by family.
(() => {
  const form = document.querySelector("[data-atlas-find]");
  if (!form) return;
  const input = form.querySelector("input");
  const none = form.querySelector(".atlas-none");
  const families = [...document.querySelectorAll(".family")];
  const fold = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  input.addEventListener("input", () => {
    const q = fold(input.value);
    let hits = 0;
    for (const fam of families) {
      let shown = 0;
      for (const li of fam.querySelectorAll("li")) {
        const ok = !q || fold(li.dataset.q).includes(q);
        li.hidden = !ok;
        shown += ok;
      }
      fam.hidden = q !== "" && shown === 0;
      fam.open = q !== "" && shown > 0;
      hits += shown;
    }
    for (const group of document.querySelectorAll(".depth-group")) {
      group.hidden = !group.querySelector(".family:not([hidden])");
    }
    none.hidden = !q || hits > 0;
    none.textContent = none.hidden ? "" : form.dataset.none;
  });
})();
