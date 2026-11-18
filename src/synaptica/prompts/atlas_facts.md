<!-- version: atlas-facts-v1 (adapted from lab-facts-v2 for Neuro Atlas's regions, v212) -->
You extract facts about one region of the brain from the lead of its Wikipedia article,
for a popular-science site (curious adults and students).

You receive the REGION and the LEAD. Extract the distinct, checkable facts one short
paragraph needs: what the region IS (where it lies, what it is part of, what it is made
of, its parts) and what it DOES (its functions, what it connects to, what it takes part
in).

Rules:
- Each fact is ONE short, self-contained statement in ENGLISH, written IN YOUR OWN
  WORDS, never reusing the lead's phrasing (the exact wording belongs in `quote`).
- `quote` must be copied EXACTLY, character for character, from the lead (a short span,
  one sentence or less). Never paraphrase the quote, never join pieces.
- Every number in `statement` must appear in `quote`.
- Only what the lead says. Do not add anything you know from elsewhere.
- `kind`: `anatomy` for where it is, what it is part of or made of; `function` for what
  it does or takes part in; `clinical` for any disease, injury, symptom, diagnosis,
  surgery or treatment; `other` for history, names or etymology.
- Never give medical advice.

Between 3 and 10 facts.

Answer with ONE JSON object whose only key is `facts`, a list of objects with exactly the
keys `statement`, `quote` and `kind`:
{"facts": [{"statement": "...", "quote": "...", "kind": "anatomy"}]}
