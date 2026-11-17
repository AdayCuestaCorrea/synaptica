"""Metrics of the news classifier against hand labels (plan, steps 14a and 14b).

Copied and adapted from paleo-atlas ``src/paleo/news/evaluate.py`` (decision D2): the
per-class precision, recall and F1, macro F1, accuracy and confusion matrix, and the
classical baseline — TF-IDF of character 2-5-grams + logistic regression, scored with
cross-validation so it is never scored on what it was trained on — and, for the
grouping (step 15), the pair precision, recall and F1 of the LLM's stored answers and of
TF-IDF similarity with a cross-validated threshold. Removed: taxa and the blind sample.

Pair labels (``eval/news/pairs.csv``: ``key_a,key_b,same`` with yes/no) are made by
Aday (not health content; plan, step 15) on the blind sheet of ``news.pair_sheet``. The
file holds only keys and answers (decision of Aday, option A, 2026-11-14): the repository
is public and the feeds' summaries (ScienceDaily's) are copyrighted, so the texts the
TF-IDF baseline needs are read from the warehouse (``fct_news_item``).

The gold labels (``eval/news/labels.csv``: ``key,type`` only) come from Sofía through
her review page (step 14b, option C; ``news.labels``), written by ``syn eval labels-gold``.
For the same reason as the pairs, the texts the baseline learns from are read from the
warehouse: what the classifier saw (``labels.label_texts``). The LLM's answer is never a
label. Needs the ``eval`` dependency group (scikit-learn).
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from synaptica.news.classify import TYPES

FOLDS = 5
SEED = 7


GOLD_COLUMNS = ("key", "type")


def load_gold(path: Path) -> list[dict[str, str]]:
    """Rows ``{key, type}``. Any other column is refused (texts never go in the
    repository), and so is a type outside :data:`TYPES`."""
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = tuple(reader.fieldnames or ())
    if columns != GOLD_COLUMNS:
        raise ValueError(f"{path} must have exactly the columns {','.join(GOLD_COLUMNS)} "
                         f"(found {','.join(columns)})")  # fmt: skip
    bad = [r["key"] for r in rows if r["type"] not in TYPES]
    if bad:
        raise ValueError(f"unknown type in {path}: {bad[:5]}")
    return rows


def scores(gold: Sequence[str], pred: Sequence[str | None]) -> dict[str, Any]:
    """Per-class precision/recall/F1/support, macro F1 (over classes present in the
    gold), accuracy and confusion matrix (rows: gold); a missing prediction is wrong."""
    per = {}
    pairs = list(zip(gold, pred, strict=True))
    for c in TYPES:
        tp = sum(g == c and p == c for g, p in pairs)
        fp = sum(g != c and p == c for g, p in pairs)
        fn = sum(g == c and p != c for g, p in pairs)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per[c] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    present = [c for c in TYPES if per[c]["support"]]
    return {
        "n": len(pairs),
        "accuracy": sum(g == p for g, p in pairs) / len(pairs) if pairs else 0.0,
        "macro_f1": sum(per[c]["f1"] for c in present) / len(present) if present else 0.0,
        "per_class": per,
        "confusion": {g: dict(Counter(p for gg, p in pairs if gg == g)) for g in TYPES},
    }


def baseline_predictions(texts: Sequence[str], gold: Sequence[str]) -> list[str]:
    """Cross-validated predictions of TF-IDF (character 2-5-grams) + logistic regression."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline

    model = make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True),
        LogisticRegression(max_iter=2_000, class_weight="balanced"),
    )
    smallest = min(Counter(gold).values())
    folds = StratifiedKFold(n_splits=max(2, min(FOLDS, smallest)), shuffle=True,
                            random_state=SEED)  # fmt: skip
    return [str(p) for p in cross_val_predict(model, list(texts), list(gold), cv=folds)]


def evaluate(
    gold: list[dict[str, str]], llm_types: dict[str, str], texts: dict[str, str]
) -> dict[str, Any]:
    """Scores of the LLM (its stored answers) on the whole gold, and of the baseline and
    the LLM on the items whose text is still in the warehouse (the baseline needs it)."""
    labels = [r["type"] for r in gold]
    out: dict[str, Any] = {"labelled": len(gold), "support": dict(Counter(labels))}
    out["llm"] = scores(labels, [llm_types.get(r["key"]) for r in gold])
    out["llm_missing"] = sum(r["key"] not in llm_types for r in gold)
    known = [r for r in gold if texts.get(r["key"])]
    out["no_text"] = len(gold) - len(known)
    seen = [r["type"] for r in known]
    if len(set(seen)) > 1 and min(Counter(seen).values()) >= 2:
        out["baseline"] = scores(seen, baseline_predictions([texts[r["key"]] for r in known], seen))
        if out["no_text"]:  # the LLM on the very same items, to compare like with like
            out["llm_same_items"] = scores(seen, [llm_types.get(r["key"]) for r in known])
    return out


def report_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Neuro News classifier — evaluation",
        "",
        f"{result['labelled']} items labelled by hand. Support: "
        + ", ".join(f"{k} {v}" for k, v in sorted(result["support"].items())) + ".",
        "",
        "| Configuration | Macro F1 | Accuracy | " + " | ".join(f"F1 {c}" for c in TYPES) + " |",
        "|---|---:|---:|" + "---:|" * len(TYPES),
    ]  # fmt: skip
    for name in ("llm", "llm_same_items", "baseline"):
        if name not in result:
            continue
        r = result[name]
        lines.append(
            f"| {name} | {r['macro_f1']:.2f} | {100 * r['accuracy']:.0f} % | "
            + " | ".join(f"{r['per_class'][c]['f1']:.2f}" for c in TYPES) + " |"
        )  # fmt: skip
    if result["llm_missing"]:
        lines += ["", f"{result['llm_missing']} labelled items have no LLM answer yet "
                      "(counted as wrong)."]  # fmt: skip
    if result.get("no_text"):
        lines += ["", f"{result['no_text']} labelled items are no longer in the warehouse: "
                      "the baseline (and `llm_same_items`) leave them out."]  # fmt: skip
    if "baseline" not in result:
        lines += ["", "Baseline not scored: it needs two classes with two items each."]
    return "\n".join(lines) + "\n"


# --- grouping (step 15) -------------------------------------------------------------


PAIR_COLUMNS = ("key_a", "key_b", "same")


def load_pairs(path: Path) -> list[dict[str, Any]]:
    """Rows ``{key_a, key_b, same}``. Any other column is refused: texts never go in the
    repository (see the module docstring); ``syn eval pairs-gold`` strips the sheet."""
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = tuple(reader.fieldnames or ())
    if columns != PAIR_COLUMNS:
        want, got = ",".join(PAIR_COLUMNS), ",".join(columns)
        raise ValueError(f"{path} must have exactly the columns {want} "
                         f"(texts are read from the warehouse), not {got}")  # fmt: skip
    bad = [r for r in rows if r["same"] not in ("yes", "no")]
    if bad:
        raise ValueError(f"'same' must be yes or no in {path}: {bad[:2]}")
    return [{**r, "same": r["same"] == "yes"} for r in rows]


def news_texts(keys: Sequence[str], warehouse: Path) -> dict[str, dict[str, Any]]:
    """Key -> {lang, outlet, title, summary, published} from ``fct_news_item``, whatever
    its date or type (the gold may be older than the grouping's look-back window)."""
    import duckdb

    wanted = sorted(set(keys))
    if not wanted:
        return {}
    with duckdb.connect(str(warehouse), read_only=True) as con:
        rows = con.execute(
            "select news_item_id, lang, outlet, title, feed_summary, published_at "
            "from fct_news_item where news_item_id in (select unnest(?))",
            [wanted],
        ).fetchall()
    return {
        k: {"lang": lang, "outlet": outlet, "title": title or "", "summary": summary or "",
            "published": published}
        for k, lang, outlet, title, summary, published in rows
    }  # fmt: skip


def pair_text(item: dict[str, Any]) -> str:
    """What TF-IDF compares: the title and the feed's summary."""
    return f"{item['title']} {item['summary']}".strip()


def load_answers(path: Path) -> dict[tuple[str, str], bool]:
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {(r["key_a"], r["key_b"]): r["same"] for r in rows}


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return precision, recall, (2 * precision * recall / (precision + recall) if tp else 0.0)


def judged_scores(
    answers: dict[tuple[str, str], bool], pairs: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Pair precision/recall/F1 of yes/no answers (an unanswered pair counts as no)."""
    said = [answers.get((p["key_a"], p["key_b"])) is True for p in pairs]
    tp = sum(s and p["same"] for s, p in zip(said, pairs, strict=True))
    fp = sum(s and not p["same"] for s, p in zip(said, pairs, strict=True))
    fn = sum(not s and p["same"] for s, p in zip(said, pairs, strict=True))
    precision, recall, f1 = _prf(tp, fp, fn)
    return {"pairs": len(pairs), "same": tp + fn, "precision": precision, "recall": recall,
            "f1": f1, "threshold": None}  # fmt: skip


def grouping_scores(sims: Sequence[float], same: Sequence[bool]) -> dict[str, Any]:
    """Cross-validated pair precision/recall/F1: each fold's threshold is the one with
    the best F1 on the other folds (copied from Paleo). Also the threshold on all pairs."""
    s, y = np.asarray(sims, dtype=float), np.asarray(same, dtype=bool)
    values = np.unique(np.round(s, 3))
    candidates = (values[:-1] + values[1:]) / 2 if len(values) > 1 else values

    def f1_at(idx: np.ndarray, t: float) -> float:
        pred = s[idx] >= t
        yy = y[idx]
        return _prf(int((pred & yy).sum()), int((pred & ~yy).sum()), int((~pred & yy).sum()))[2]

    def best(idx: np.ndarray) -> float:
        f1s = np.array([f1_at(idx, t) for t in candidates])
        return float(np.median(candidates[f1s == f1s.max()]))

    order = np.random.default_rng(SEED).permutation(len(s))
    pred = np.zeros(len(s), dtype=bool)
    for fold in np.array_split(order, min(FOLDS, len(s))):
        pred[fold] = s[fold] >= best(np.setdiff1d(order, fold))
    precision, recall, f1 = _prf(int((pred & y).sum()), int((pred & ~y).sum()),
                                 int((~pred & y).sum()))  # fmt: skip
    return {"pairs": len(s), "same": int(y.sum()), "precision": precision, "recall": recall,
            "f1": f1, "threshold": best(order)}  # fmt: skip


def evaluate_pairs(
    pairs: list[dict[str, Any]],
    answers: dict[tuple[str, str], bool],
    texts: dict[str, str],
) -> dict[str, Any]:
    """The LLM's answers on every labelled pair; TF-IDF on the pairs whose two texts are
    in ``texts`` (key -> text, from the warehouse). ``missing``: keys without text."""
    from synaptica.news.group import tfidf_similarity

    out = {"llm": judged_scores(answers, pairs)}
    have = [p for p in pairs if p["key_a"] in texts and p["key_b"] in texts]
    if len(have) >= 2 and len({p["same"] for p in have}) == 2:
        matrix = tfidf_similarity([texts[p[k]] for p in have for k in ("key_a", "key_b")])
        sims = [matrix[2 * i, 2 * i + 1] for i in range(len(have))]
        out["tfidf"] = grouping_scores(sims, [p["same"] for p in have])
    out["missing"] = sorted({p[k] for p in pairs for k in ("key_a", "key_b")} - set(texts))
    return out


def pairs_markdown(result: dict[str, Any]) -> str:
    lines = ["## Same story (grouping)", "",
             "| Method | Pairs (same) | Precision | Recall | F1 | Threshold |",
             "|---|---:|---:|---:|---:|---:|"]  # fmt: skip
    for name, g in result.items():
        if name == "missing":
            continue
        cut = "—" if g["threshold"] is None else f"{g['threshold']:.3f}"
        lines.append(f"| {name} | {g['pairs']} ({g['same']}) | {g['precision']:.2f} | "
                     f"{g['recall']:.2f} | {g['f1']:.2f} | {cut} |")  # fmt: skip
    if result.get("missing"):
        shown = ", ".join(result["missing"][:5]) + ("…" if len(result["missing"]) > 5 else "")
        lines += ["", f"Not in the warehouse (left out of TF-IDF): "
                  f"{len(result['missing'])} items ({shown})."]  # fmt: skip
    lines += ["", "The pairs come from the blind sheet (`syn eval pairs-sheet`), which picks "
              "the likely duplicates, not a uniform sample: these figures describe those pairs, "
              "not the whole stream."]  # fmt: skip
    return "\n".join(lines) + "\n"
