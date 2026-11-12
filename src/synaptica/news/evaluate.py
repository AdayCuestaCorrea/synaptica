"""Metrics of the news classifier against hand labels (plan, steps 14a and 14b).

Copied and adapted from paleo-atlas ``src/paleo/news/evaluate.py`` (decision D2): the
per-class precision, recall and F1, macro F1, accuracy and confusion matrix, and the
classical baseline — TF-IDF of character 2-5-grams + logistic regression, scored with
cross-validation so it is never scored on what it was trained on. Removed: taxa,
grouping (step 15 adds its own) and the blind-sample section.

The gold labels (``eval/news/labels.csv``: ``key,lang,text,type``) come from Sofía
through the review flow (step 14b, after D5); until then the command works on any file
with that shape, and the tests use a small synthetic one. The LLM's answer is never a
label. Needs the ``eval`` dependency group (scikit-learn).
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from synaptica.news.classify import TYPES

FOLDS = 5
SEED = 7


def load_gold(path: Path) -> list[dict[str, str]]:
    """Rows ``{key, lang, text, type}``; a type outside :data:`TYPES` is an error."""
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
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


def evaluate(gold: list[dict[str, str]], llm_types: dict[str, str]) -> dict[str, Any]:
    """Scores of the LLM (its stored answers) and of the baseline on the same gold."""
    labels = [r["type"] for r in gold]
    out: dict[str, Any] = {"labelled": len(gold), "support": dict(Counter(labels))}
    out["llm"] = scores(labels, [llm_types.get(r["key"]) for r in gold])
    out["llm_missing"] = sum(r["key"] not in llm_types for r in gold)
    if len(set(labels)) > 1 and min(Counter(labels).values()) >= 2:
        out["baseline"] = scores(labels, baseline_predictions([r["text"] for r in gold], labels))
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
    for name in ("llm", "baseline"):
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
    if "baseline" not in result:
        lines += ["", "Baseline not scored: it needs two classes with two items each."]
    return "\n".join(lines) + "\n"
