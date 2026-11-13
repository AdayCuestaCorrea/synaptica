"""Step 18 of plan-fase-1: the S5 chain again, with the v2 prompts and the package code.

The same 10 articles Sofía reviewed blind in S5 (the cached efetch of
``data/cache/s5/pubmed``; ``fetch_articles`` of ``pipeline.py``, same filters, never the
network), through what will run in production: ``narrative.facts`` → ``narrative.write``
(English, Spanish, the checks, the new ones included) → ``narrative.judge``. Each writer
gets its own folder, so the two runs never share texts; the LLM cache and the Groq quota
log are those of ``SYN_DATA_DIR``. A run stopped by the Groq quota resumes where it
stopped: facts and texts already up to date with the v2 prompts are not asked again.

    SYN_DATA_DIR=~/synaptica-data uv run --env-file .env python spikes/s5/rerun_v2.py \\
        --writer ollama:paleo-qwen3.5-9b --judge groq:openai/gpt-oss-120b \\
        --out ~/synaptica-data/runs/18/qwen9b

Writes ``summary.json`` in ``--out``: per article, the facts, both texts with their
status and problems, and the judge's verdict.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from synaptica.config import project_root
from synaptica.llm import LLM, LLMOutputError, QuotaExhausted
from synaptica.narrative import facts as facts_mod
from synaptica.narrative import judge as judge_mod
from synaptica.narrative import write as write_mod

EFETCH = project_root() / "data" / "cache" / "s5" / "pubmed" / "efetch_20261102.xml"
S5_RUN = (
    Path(__file__).parent
    / "results"
    / ("run_ollama-paleo-qwen3.5-9b-groq-openai-gpt-oss-120b.json")
)
SKIP_TYPES = {"Erratum", "Published Erratum", "Comment", "Editorial", "Letter", "News",
              "Retraction of Publication", "Retracted Publication"}  # fmt: skip


def articles() -> list[dict[str, str]]:
    """The S5 articles, read as ``pipeline.fetch_articles`` read them."""
    out = []
    for node in ET.parse(EFETCH).getroot().iter("PubmedArticle"):
        types = {t.text for t in node.iter("PublicationType")}
        parts = [(f"{p.get('Label')}: " if p.get("Label") else "") + "".join(p.itertext()).strip()
                 for p in node.iter("AbstractText")]  # fmt: skip
        abstract = "\n".join(p for p in parts if p)
        if types & SKIP_TYPES or len(abstract) < 600 or node.findtext(".//Language") != "eng":
            continue
        title = "".join(node.find(".//ArticleTitle").itertext()).strip()
        out.append({"pmid": node.findtext(".//PMID"), "title": title, "abstract": abstract})
        if len(out) == 10:
            break
    expected = [a["pmid"] for a in json.loads(S5_RUN.read_text("utf-8"))["articles"]]
    assert [a["pmid"] for a in out] == expected, "not the articles Sofía reviewed"
    return out


def make(spec: str) -> LLM:
    provider, model = spec.split(":", 1)
    return LLM(provider, model)


def run_article(art: dict, writer: LLM, judge: LLM, out: Path) -> dict:
    derived, cache = out / "derived", out / "cache"
    study = {"study_id": f"pmid:{art['pmid']}", "pmid": art["pmid"], "title": art["title"]}
    sid, abstract = study["study_id"], art["abstract"]
    if not facts_mod.is_up_to_date(sid, abstract, derived):
        facts_mod.extract_facts(writer, study, abstract, origin="pubmed",
                                derived_root=derived, cache_root=cache)  # fmt: skip
    doc = facts_mod.load(facts_mod.facts_path(sid, derived))
    row = {"pmid": art["pmid"], "title": art["title"], "facts": doc["status"],
           "n_facts": len(doc["facts"]), "rejected_facts": doc["rejected"]}  # fmt: skip
    if doc["status"] != "ok":
        return row
    if not write_mod.is_up_to_date(doc, derived):
        quotes = json.loads(facts_mod.quotes_path(sid, cache).read_text("utf-8"))
        write_mod.write_study(writer, doc, quotes, abstract, derived_root=derived)
    if texts := judge_mod.pending(sid, derived):
        judge_mod.judge_study(judge, study, abstract, texts, derived_root=derived)
    for lang in ("en", "es"):
        for verified in (True, False):
            path = write_mod.text_path(sid, lang, verified=verified, derived_root=derived)
            if path.exists():
                rec = json.loads(path.read_text("utf-8"))
                row[lang] = {k: rec.get(k) for k in ("status", "problems", "sentences", "judge")}
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--writer", required=True, help="provider:model")
    ap.add_argument("--judge", required=True, help="provider:model (another family)")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    writer, judge = make(args.writer), make(args.judge)
    rows, stopped = [], None
    for art in articles():
        try:
            row = run_article(art, writer, judge, args.out)
        except QuotaExhausted as exc:
            stopped = f"{art['pmid']}: {exc}"
            print(f"  quota used up at {stopped}; run again tomorrow to resume")
            break
        except LLMOutputError as exc:  # as the pipeline: that study fails, the rest go on
            print(f"  {art['pmid']}: invalid output from the model")
            rows.append({"pmid": art["pmid"], "title": art["title"], "error": str(exc)[:300]})
            continue
        status = (row.get("en") or {}).get("status"), (row.get("es") or {}).get("status")
        print(f"  {art['pmid']}: facts {row['facts']}, texts {status}")
        rows.append(row)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps({
        "measured_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "writer": writer.label, "judge": judge.label, "stopped": stopped,
        "writer_stats": vars(writer.stats), "judge_stats": vars(judge.stats),
        "articles": rows,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")  # fmt: skip


if __name__ == "__main__":
    main()
