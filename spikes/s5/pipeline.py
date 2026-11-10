"""S5 · Trial of the text chain on 10 PubMed articles: facts -> EN -> ES -> checks -> judge.

The chain follows Paleo Atlas (``narrative/facts.py`` and ``narrative/write.py``): facts
with a verbatim quote from the abstract, checked deterministically; an English summary
whose sentences cite their facts, checked (citations, numbers, names, no 8-word copied
run); a Spanish adaptation checked for alignment; with one retry that feeds back the
failures, as in ``write_page``. New here: an independent judge from another model
family reads the abstract and the summary.

Abstracts come from PubMed ``efetch`` into ``data/cache/s5/pubmed/`` (git-ignored) and are
never written to the repository: ``results/`` keeps PMIDs, metrics and our own summaries
only. Run from the repo root:

    uv run --group spike-s5 --env-file .env python spikes/s5/pipeline.py \\
        --writer ollama:paleo-qwen3.5-9b --judge groq:openai/gpt-oss-120b
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

import httpx
from checks import check_alignment, check_fact, check_text
from llm import CACHE, LLM, LLMOutputError
from pydantic import BaseModel, Field

from synaptica.config import CONTACT_EMAIL, USER_AGENT

HERE = Path(__file__).parent
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# Same broad query as spikes/s1/pubmed.py; fixed week so the trial is reproducible.
TERM = (
    '"nervous system"[MeSH] OR "nervous system diseases"[MeSH] OR brain[tiab] '
    "OR neuron*[tiab] OR neural[tiab] OR cortex[tiab] OR synap*[tiab]"
)
WINDOW = ("2026/11/02", "2026/11/08")
N_ARTICLES = 10
SKIP_TYPES = {"Erratum", "Published Erratum", "Comment", "Editorial", "Letter", "News",
              "Retraction of Publication", "Retracted Publication"}  # fmt: skip
MIN_FACTS = 3


# --------------------------------------------------------------------------- PubMed


def fetch_articles() -> list[dict[str, str]]:
    """10 recent research articles with an abstract; the XML is cached, never versioned."""
    path = CACHE / "pubmed" / f"efetch_{WINDOW[0].replace('/', '')}.xml"
    if not path.exists():
        params = {"db": "pubmed", "tool": "synaptica", "email": CONTACT_EMAIL}
        if key := os.environ.get("NCBI_API_KEY"):
            params["api_key"] = key
        with httpx.Client(timeout=60, headers={"User-Agent": USER_AGENT}) as c:
            r = c.get(f"{EUTILS}/esearch.fcgi", params={
                **params, "term": f"({TERM}) AND hasabstract", "datetype": "edat",
                "mindate": WINDOW[0], "maxdate": WINDOW[1], "retmax": 60, "retmode": "json",
                "sort": "pub_date"})  # fmt: skip
            ids = r.raise_for_status().json()["esearchresult"]["idlist"]
            time.sleep(0.5)
            r = c.get(f"{EUTILS}/efetch.fcgi",
                      params={**params, "id": ",".join(ids), "retmode": "xml"})  # fmt: skip
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(r.raise_for_status().text, encoding="utf-8")
    articles = []
    for node in ET.parse(path).getroot().iter("PubmedArticle"):
        types = {t.text for t in node.iter("PublicationType")}
        parts = [
            (f"{p.get('Label')}: " if p.get("Label") else "") + "".join(p.itertext()).strip()
            for p in node.iter("AbstractText")
        ]
        abstract = "\n".join(p for p in parts if p)
        lang = node.findtext(".//Language") or ""
        if types & SKIP_TYPES or len(abstract) < 600 or lang != "eng":
            continue
        title = "".join(node.find(".//ArticleTitle").itertext()).strip()
        articles.append(
            {
                "pmid": node.findtext(".//PMID"),
                "title": title,
                "abstract": abstract,
                "types": sorted(types),
            }
        )
        if len(articles) == N_ARTICLES:
            break
    return articles


# --------------------------------------------------------------------------- schemas


class Fact(BaseModel):
    statement: str = Field(description="one self-contained fact, in English, own words")
    quote: str = Field(description="exact span copied from the abstract")
    subject: Literal["humans", "animals", "cells_or_tissue", "computational", "other"]


class Extraction(BaseModel):
    facts: list[Fact]


class Sentence(BaseModel):
    text: str
    fact_ids: list[str] = Field(description="ids of the facts this sentence relies on")


class Summary(BaseModel):
    sentences: list[Sentence]


class Adapted(BaseModel):
    index: int = Field(description="index of the English sentence, starting at 1")
    text: str = Field(description="the Spanish version of that sentence")


class AdaptedText(BaseModel):
    sentences: list[Adapted]


class Verdict(BaseModel):
    faithful: bool
    no_overclaim: bool
    no_medical_advice: bool
    spanish_matches: bool
    passed: bool
    reason: str = ""
    # Not a gate: orders Sofía's queue (judge-v2, after her S5 review).
    spanish_natural: int = Field(ge=1, le=5, description="1-5, how natural the Spanish reads")


def prompt(name: str) -> str:
    return (HERE / "prompts" / f"{name}.md").read_text("utf-8").split("\n", 1)[1].strip()


# --------------------------------------------------------------------------- chain


def write_en(writer: LLM, facts: dict[str, str], feedback: list[str]) -> list[tuple[str, list]]:
    lines = ["VERIFIED FACTS:", *(f"{k} {v}" for k, v in facts.items())]
    if feedback:
        lines += ["", "Your previous answer failed these automatic checks. Fix every one:",
                  *feedback,
                  "A number must be written exactly as in a cited fact or dropped; a name must "
                  "appear in the facts; a copied run of words must be rephrased."]  # fmt: skip
    out = writer.complete_json(prompt("write_en"), "\n".join(lines), Summary, max_tokens=1_500)
    return [(s.text.strip(), s.fact_ids) for s in out.sentences]


def adapt_es(writer: LLM, en: list[str], feedback: list[str]) -> list[str]:
    lines = ["FRASES EN INGLÉS:", *(f"{i}. {t}" for i, t in enumerate(en, start=1))]
    if feedback:
        lines += ["", "Tu respuesta anterior no pasó estas comprobaciones. Corrígelas todas:",
                  *feedback]  # fmt: skip
    out = writer.complete_json(prompt("adapt_es"), "\n".join(lines), AdaptedText, max_tokens=1_500)
    by_index = {s.index: s.text.strip() for s in out.sentences}
    return [by_index.get(i, "") for i in range(1, len(en) + 1)]


def run_article(art: dict[str, str], writer: LLM, judge: LLM | None) -> dict[str, object]:
    row: dict[str, object] = {"pmid": art["pmid"], "types": art["types"]}
    w0 = writer.stats.snapshot()
    started = time.monotonic()
    # 1. Facts, each checked against the abstract.
    try:
        ext = writer.complete_json(
            prompt("extract_facts"),
            f"TITLE: {art['title']}\n\nABSTRACT:\n{art['abstract']}",
            Extraction,
            max_tokens=2_000,
        )
    except LLMOutputError as exc:
        row.update(status="failed", stage="facts", error=str(exc)[:200])
        return row
    # The writer sees the statements; the checks also accept what the quote says.
    facts: dict[str, str] = {}
    support: dict[str, str] = {}
    rejected = []
    for fact in ext.facts:
        if reason := check_fact(fact.statement, fact.quote, art["abstract"]):
            rejected.append(reason.split(":")[0])
        else:
            fid = f"f{len(facts) + 1}"
            facts[fid] = f"[{fact.subject}] {fact.statement}"
            support[fid] = f"{fact.statement} {fact.quote}"
    row["facts"] = {"accepted": len(facts), "rejected": len(rejected), "reasons": rejected}
    row["subjects"] = sorted({f.subject for f in ext.facts})
    if len(facts) < MIN_FACTS:
        row.update(status="failed", stage="facts", tokens=writer.stats.since(w0))
        return row
    # 2. English summary + checks, one retry with feedback.
    feedback: list[str] = []
    for attempt in range(1, 3):
        row["en_attempts"] = attempt
        en = write_en(writer, facts, feedback)
        report = check_text(en, support, [art["abstract"]])
        feedback = report.summary()
        if report.passed:
            break
    # A failed text may contain a run copied from the abstract: neither it nor the quoted
    # run in the problem message goes to results/.
    row["en_problems"] = [
        re.sub(r" \('.*?'\)|: '.*'$", "", p) for p in feedback
    ]  # "sentence 1: copies 8+ words from a source"
    if feedback:
        row.update(status="failed", stage="en", tokens=writer.stats.since(w0))
        return row
    # 3. Spanish adaptation + alignment, one retry.
    en_texts = [t for t, _ in en]
    feedback = []
    for attempt in range(1, 3):
        row["es_attempts"] = attempt
        es = adapt_es(writer, en_texts, feedback)
        feedback = check_alignment(en_texts, es)
        if not feedback:
            break
    row["es_problems"] = feedback
    row["en"], row["es"] = en_texts, es
    row["writer_tokens"] = writer.stats.since(w0)
    row["writer_seconds"] = round(time.monotonic() - started, 1)
    if feedback:
        row.update(status="failed", stage="es")
        return row
    row["checks_passed"] = True
    # 4. Judge from another model family.
    if judge is None:
        row["status"] = "checks_passed_no_judge"
        return row
    j0 = judge.stats.snapshot()
    summary = "\n".join(f"EN {i}. {t}" for i, t in enumerate(en_texts, 1))
    summary += "\n" + "\n".join(f"ES {i}. {t}" for i, t in enumerate(es, 1))
    try:
        verdict = judge.complete_json(
            prompt("judge"),
            f"TITLE: {art['title']}\n\nABSTRACT:\n{art['abstract']}\n\nSUMMARY:\n{summary}",
            Verdict,
            max_tokens=800,
        )
    except LLMOutputError as exc:
        row.update(status="failed", stage="judge", error=str(exc)[:200])
        return row
    row["judge"] = verdict.model_dump()
    row["judge_tokens"] = judge.stats.since(j0)
    row["status"] = "published" if verdict.passed else "rejected_by_judge"
    return row


def make(spec: str) -> LLM:
    provider, model = spec.split(":", 1)
    return LLM(provider, model)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--writer", required=True, help="provider:model")
    ap.add_argument("--judge", default="none", help="provider:model or none")
    args = ap.parse_args()
    writer = make(args.writer)
    judge = None if args.judge == "none" else make(args.judge)
    articles = fetch_articles()
    print(f"{len(articles)} articles; writer {writer.label}; judge {judge and judge.label}")
    rows = []
    for art in articles:
        row = run_article(art, writer, judge)
        print(f"  {row['pmid']}: {row['status']} {row.get('stage', '')}")
        rows.append(row)
    slug = re.sub(r"[^a-z0-9.]+", "-", f"{args.writer}--{args.judge}".lower())
    out = HERE / "results" / f"run_{slug}.json"
    out.write_text(
        json.dumps(
            {
                "measured_at": dt.datetime.now(dt.UTC).isoformat(),
                "writer": writer.label,
                "judge": judge and judge.label,
                "window": WINDOW,
                "writer_stats": vars(writer.stats),
                "judge_stats": judge and vars(judge.stats),
                "articles": rows,
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"-> {out.relative_to(HERE.parents[1])}")


if __name__ == "__main__":
    main()
