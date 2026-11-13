"""Command-line entry point: ``syn <command>``.

Adapted from paleo-atlas ``src/paleo/cli.py``. Every pipeline step is a command with a
reliable exit code, so GitHub Actions (or any orchestrator) calls exactly the same thing.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from synaptica import __version__, config

app = typer.Typer(help="SYNAPTICA data pipeline.", no_args_is_help=True)
report_app = typer.Typer(help="Run log in data/runs/ (one record per pipeline run).")
app.add_typer(report_app, name="report")
ingest_app = typer.Typer(help="Download new items from each source to data/raw/.")
app.add_typer(ingest_app, name="ingest")
news_app = typer.Typer(help="Neuro News: neuroscience filter, type and grouping.")
app.add_typer(news_app, name="news")
eval_app = typer.Typer(help="Evaluations against hand labels (eval/).")
app.add_typer(eval_app, name="eval")
review_app = typer.Typer(help="Sofía's review queue: her page and her Issues (ADR 0005).")
app.add_typer(review_app, name="review")


def _llm(provider: str | None, model: str | None):
    """The LLM to use, or None: no model is called unless a provider is given."""
    if provider is None:
        return None
    from synaptica.llm import LLM

    return LLM(provider, model or DEFAULT_MODELS[provider])


# Decision D4: Groq's writer model in Actions; Qwen 9B for the local initial load.
DEFAULT_MODELS = {"groq": "qwen/qwen3.8-27b", "ollama": "paleo-qwen3.5-9b"}
ProviderOption = Annotated[
    str | None, typer.Option(help="groq or ollama; without it, no model is called.")
]
ModelOption = Annotated[str | None, typer.Option(help="Model name (default per provider).")]

REQUIRED_PYTHON = (3, 14)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"syn {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    version: Annotated[
        bool,
        typer.Option("--version", callback=_show_version, is_eager=True, help="Show the version."),
    ] = False,
) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def run_checks() -> list[Check]:
    """Environment checks for `syn doctor`. No network access."""
    py = sys.version_info[:2]
    checks = [
        Check(
            "Python",
            py == REQUIRED_PYTHON,
            f"{py[0]}.{py[1]} (needs {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]})",
        ),
        Check(
            "git",
            shutil.which("git") is not None,
            "on PATH" if shutil.which("git") else "not found",
        ),
    ]
    data = config.get_paths().data
    checks.append(
        Check(
            "Data directory",
            True,
            f"{data} ({'exists' if data.is_dir() else 'not created yet'})",
            required=False,
        )
    )
    for var in config.ENV_VARS:
        is_set = bool(os.environ.get(var.name))
        checks.append(
            Check(
                var.name,
                is_set or not var.required,
                f"{'set' if is_set else 'not set'} · {var.purpose}",
                required=var.required,
            )
        )
    return checks


@app.command()
def doctor() -> None:
    """Check the environment and the variables the pipeline needs (exit 1 on a failure)."""
    checks = run_checks()
    for c in checks:
        mark = "✓" if c.ok else "✗"
        note = "" if c.required else " (optional)"
        typer.echo(f"{mark} {c.name}{note}: {c.detail}")
    if any(c.required and not c.ok for c in checks):
        raise typer.Exit(code=1)


@report_app.command("start")
def report_start(
    trigger: Annotated[str, typer.Option(help="schedule, backup, manual or local.")] = "local",
    changed: Annotated[bool, typer.Option(help="Change detection found something new.")] = True,
) -> None:
    """Record that a run started and what change detection found (data/runs/)."""
    from synaptica import report

    try:
        run = report.start_run(config.get_paths().data, trigger=trigger, changed=changed)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--trigger") from exc
    typer.echo(f"Run started {run['started_at']} ({trigger}, changed={changed})")


@report_app.command("finish")
def report_finish(
    jobs: Annotated[
        Path | None, typer.Option(help="GitHub API dump of this run's jobs (step durations).")
    ] = None,
) -> None:
    """Complete the current run record and print the report as Markdown."""
    from synaptica import report

    try:
        run = report.finish_run(
            config.get_paths().data,
            run_results=config.project_root() / "dbt" / "target" / "run_results.json",
            jobs=jobs,
        )
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(report.markdown(run))


@report_app.command("ran-today")
def report_ran_today() -> None:
    """Exit 0 if a run already finished without failures today (UTC), 1 otherwise."""
    from synaptica import report

    raise typer.Exit(0 if report.ran_today(config.get_paths().data) else 1)


@ingest_app.command("pubmed")
def ingest_pubmed(
    days: Annotated[
        int, typer.Option(min=1, max=30, help="Records that entered PubMed in the last N days.")
    ] = 3,
) -> None:
    """New neuroscience records from PubMed: metadata, MeSH; abstracts only to the cache."""
    from synaptica.http import HttpError, make_client
    from synaptica.ingest import pubmed

    try:
        with make_client() as client:
            result = pubmed.ingest(client, days=days)
    except HttpError as exc:
        typer.echo(f"PubMed failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"PubMed: {result.found} records in {days} day(s); "
        f"{result.summaries_requested} new summaries ({result.summaries_new_versions} stored); "
        f"{result.medline_requested} MEDLINE records checked "
        f"({result.medline_new_versions} new versions, {result.abstracts_cached} abstracts cached)"
    )


@ingest_app.command("crossref")
def ingest_crossref(
    days: Annotated[
        int, typer.Option(min=1, max=60, help="Notices deposited in the last N days.")
    ] = 3,
) -> None:
    """Retraction, correction and other notices from Crossref, for the study signals."""
    from synaptica.http import HttpError, make_client
    from synaptica.ingest import crossref

    try:
        with make_client() as client:
            result = crossref.ingest(client, days=days)
    except HttpError as exc:
        typer.echo(f"Crossref failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    listed = ", ".join(f"{k} {v}" for k, v in result.notices.items())
    typer.echo(f"Crossref: {listed}; {result.new_versions} new or changed notices stored")


@ingest_app.command("europepmc")
def ingest_europepmc(
    days: Annotated[
        int, typer.Option(min=1, max=30, help="Open-access records indexed in the last N days.")
    ] = 3,
) -> None:
    """Open-access records from Europe PMC: metadata and licence (full text on demand)."""
    from synaptica.http import HttpError, make_client
    from synaptica.ingest import europepmc

    try:
        with make_client() as client:
            result = europepmc.ingest(client, days=days)
    except HttpError as exc:
        typer.echo(f"Europe PMC failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"Europe PMC: {result.found} open-access records in {days} day(s); "
        f"{result.new_versions} new or changed stored"
    )


@ingest_app.command("biorxiv")
def ingest_biorxiv(
    days: Annotated[
        int, typer.Option(min=1, max=60, help="Preprints posted in the last N days.")
    ] = 7,
) -> None:
    """Neuro preprints from bioRxiv and medRxiv, latest version per DOI."""
    from synaptica.http import HttpError, make_client
    from synaptica.ingest import biorxiv

    try:
        with make_client() as client:
            result = biorxiv.ingest(client, days=days)
            published = biorxiv.ingest_published(client)
    except HttpError as exc:
        typer.echo(f"bioRxiv/medRxiv failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    found = ", ".join(f"{k} {v}" for k, v in result.found.items())
    stored = ", ".join(f"{k} {v}" for k, v in result.new_versions.items())
    typer.echo(
        f"Preprints in {days} day(s): {found}; new or changed stored: {stored}; "
        f"{result.abstracts_cached} abstracts cached; published links stored: "
        + ", ".join(f"{k} {v}" for k, v in published.items())
    )


@ingest_app.command("journals")
def ingest_journals() -> None:
    """Nature, Science, Cell and sister journals: metadata and links (Crossref fallback)."""
    from synaptica.http import make_client
    from synaptica.ingest import journals

    with make_client() as client:
        result = journals.ingest(client)
    listed = ", ".join(f"{k} {v}" for k, v in result.items.items())
    typer.echo(f"Journals: {listed}; {result.new_versions} new or changed stored")
    if result.via_crossref:
        typer.echo(f"  via Crossref: {', '.join(result.via_crossref)}")
    if result.failed:
        typer.echo(f"  failed: {', '.join(result.failed)}", err=True)
        raise typer.Exit(code=1)


@ingest_app.command("news")
def ingest_news() -> None:
    """Popular-science news feeds (SINC, The Conversation, ScienceDaily)."""
    from synaptica.http import make_client
    from synaptica.ingest import news

    with make_client() as client:
        result = news.ingest(client)
    typer.echo(
        f"News: {result.items} articles in {result.feeds} feeds; "
        f"{result.new_versions} new or changed stored"
    )
    if result.failed:
        typer.echo(f"  failed: {', '.join(result.failed)}", err=True)
        raise typer.Exit(code=1)


@ingest_app.command("openalex")
def ingest_openalex() -> None:
    """OpenAlex topics and citations for the general-journal items (by DOI, filter only)."""
    from synaptica.http import HttpError, make_client
    from synaptica.ingest import openalex

    try:
        with make_client() as client:
            result = openalex.ingest(client)
    except HttpError as exc:
        typer.echo(f"OpenAlex failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"OpenAlex: {result.asked} DOIs asked, {result.found} found; {result.new_versions} stored"
    )


@news_app.command("neuro")
def news_neuro(
    provider: ProviderOption = None,
    model: ModelOption = None,
    limit: Annotated[int | None, typer.Option(help="Ask the model about N items at most.")] = None,
) -> None:
    """Which items of the general journals and feeds are neuroscience: OpenAlex rules, then
    the LLM for the rest (derived/news/neuro.json)."""
    from synaptica.llm import QuotaExhausted
    from synaptica.news import neuro

    try:
        result = neuro.decide(_llm(provider, model), limit=limit)
    except QuotaExhausted as exc:
        typer.echo(f"LLM quota used up: {exc}; the rest stays undecided", err=True)
        raise typer.Exit(code=0) from exc
    basis = ", ".join(f"{k} {v}" for k, v in (result.by_basis or {}).items())
    typer.echo(
        f"Neuro filter: {result.items} items; {basis or 'nothing decided'}; "
        f"{result.llm_asked} answered by the LLM; {result.undecided} undecided"
    )


@news_app.command("classify")
def news_classify(
    provider: ProviderOption = None,
    model: ModelOption = None,
    limit: Annotated[int | None, typer.Option(help="Classify N items at most.")] = None,
) -> None:
    """Type of the Neuro News items (studies that pass the prefilter and neuro news) with
    the LLM -> derived/news/types.json. Reads the warehouse: run `syn build` first."""
    from synaptica.llm import QuotaExhausted
    from synaptica.news import classify

    llm = _llm(provider, model)
    if llm is None:
        typer.echo("No --provider given: nothing classified.")
        raise typer.Exit(0)
    if not classify.warehouse_path().exists():
        typer.echo("No warehouse yet: run `syn build` first.", err=True)
        raise typer.Exit(1)
    try:
        result = classify.run(llm, limit=limit)
    except QuotaExhausted as exc:
        typer.echo(f"LLM quota used up: {exc}; the rest waits for the next run", err=True)
        raise typer.Exit(0) from exc
    typer.echo(
        f"Classified {result.classified} of {result.total} items "
        f"({result.up_to_date} up to date, {result.missing} left out by the model)"
    )


@news_app.command("group")
def news_group(provider: ProviderOption = None, model: ModelOption = None) -> None:
    """Group the neuro news items that tell the same story (LLM on each candidate pair)
    -> derived/news/groups.json. Reads the warehouse: run `syn build` first."""
    from synaptica.llm import QuotaExhausted
    from synaptica.news import classify, group

    llm = _llm(provider, model)
    if llm is None:
        typer.echo("No --provider given: nothing grouped.")
        raise typer.Exit(0)
    if not classify.warehouse_path().exists():
        typer.echo("No warehouse yet: run `syn build` first.", err=True)
        raise typer.Exit(1)
    try:
        result = group.run(llm)
    except QuotaExhausted as exc:
        typer.echo(f"LLM quota used up: {exc}; the rest waits for the next run", err=True)
        raise typer.Exit(0) from exc
    typer.echo(
        f"Grouping: {result['items']} items, {result['candidates']} candidate pairs, "
        f"{result['same']} same story; {result['groups']} groups ({result['grouped']} items "
        "in groups of two or more)"
    )


@eval_app.command("news")
def eval_news(
    gold: Annotated[Path, typer.Option(help="Hand labels: key,lang,text,type.")] = Path(
        "eval/news/labels.csv"
    ),
    pairs: Annotated[
        Path | None, typer.Option(help="Hand-labelled pairs: key_a,key_b,text_a,text_b,same.")
    ] = None,
    out: Annotated[Path | None, typer.Option(help="Write the Markdown report here.")] = None,
) -> None:
    """Macro F1 of the LLM's stored types and of the TF-IDF baseline on the hand labels;
    with --pairs, precision and recall of the same-story pairs."""
    from synaptica.news import classify, evaluate, group

    if not gold.exists():
        typer.echo(f"No labels at {gold} yet (Sofía's labels arrive with step 14b).", err=True)
        raise typer.Exit(1)
    llm_types = {k: r["type"] for k, r in classify.load_types(classify.types_path()).items()}
    report = evaluate.report_markdown(evaluate.evaluate(evaluate.load_gold(gold), llm_types))
    if pairs is not None:
        answers = evaluate.load_answers(group.pairs_path())
        result = evaluate.evaluate_pairs(evaluate.load_pairs(pairs), answers)
        report += "\n" + evaluate.pairs_markdown(result)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
    typer.echo(report)


LimitOption = Annotated[int | None, typer.Option(help="Call the model for N studies at most.")]
UntilOption = Annotated[
    str | None, typer.Option(help="Start no new study after this local time (HH:MM).")
]
StudyOption = Annotated[
    list[str] | None, typer.Option("--study", help="Only this study_id (repeatable).")
]


def _narrative_studies(study: list[str] | None) -> list[dict]:
    from synaptica.narrative import pipeline
    from synaptica.news import classify

    if not classify.warehouse_path().exists():
        typer.echo("No warehouse yet: run `syn build` first.", err=True)
        raise typer.Exit(1)
    return pipeline.select(study_ids=study)


def _outcomes(verb: str, result) -> str:
    counts = ", ".join(f"{k} {v}" for k, v in sorted(result.counts.items())) or "nothing new"
    line = (f"{verb} {result.done} of {result.total} studies "
            f"({result.up_to_date} up to date): {counts}")  # fmt: skip
    if result.stopped == "deadline":
        line += "; deadline reached, the rest stays pending"
    return line


def _until(until: str | None):
    import datetime as dt

    from synaptica.narrative import pipeline

    return pipeline.deadline(until, dt.datetime.now())


@app.command()
def facts(
    provider: ProviderOption = None,
    model: ModelOption = None,
    limit: LimitOption = None,
    study: StudyOption = None,
    until: UntilOption = None,
) -> None:
    """Verified facts of the studies to summarize -> derived/facts/ (quotes only in
    data/cache/). Reads the warehouse: run `syn build` and `syn news classify` first."""
    from synaptica.http import make_client
    from synaptica.llm import QuotaExhausted
    from synaptica.narrative import pipeline

    llm = _llm(provider, model)
    if llm is None:
        typer.echo("No --provider given: no facts extracted.")
        raise typer.Exit(0)
    studies = _narrative_studies(study)
    try:
        with make_client() as client:  # Europe PMC full text, on demand
            result = pipeline.run_facts(
                llm, studies, client=client, limit=limit, until=_until(until)
            )
    except QuotaExhausted as exc:
        typer.echo(f"LLM quota used up: {exc}; the rest waits for the next run", err=True)
        raise typer.Exit(0) from exc
    typer.echo(_outcomes("Facts for", result))


@app.command()
def write(
    provider: ProviderOption = None,
    model: ModelOption = None,
    limit: LimitOption = None,
    study: StudyOption = None,
    until: UntilOption = None,
) -> None:
    """English and Spanish summaries from the facts, checked -> derived/texts/ (or
    derived/texts_review/ when they fail; the site then shows the fallback text)."""
    from synaptica.llm import QuotaExhausted
    from synaptica.narrative import pipeline

    llm = _llm(provider, model)
    if llm is None:
        typer.echo("No --provider given: nothing written.")
        raise typer.Exit(0)
    studies = _narrative_studies(study)
    try:
        result = pipeline.run_write(llm, studies, limit=limit, until=_until(until))
    except QuotaExhausted as exc:
        typer.echo(f"LLM quota used up: {exc}; the rest waits for the next run", err=True)
        raise typer.Exit(0) from exc
    typer.echo(_outcomes("Wrote", result))


# Decision D4: the judge is of another family than the writer.
DEFAULT_JUDGE_MODELS = {"groq": "openai/gpt-oss-120b"}


@app.command()
def judge(
    provider: ProviderOption = None,
    model: ModelOption = None,
    limit: LimitOption = None,
    study: StudyOption = None,
    until: UntilOption = None,
) -> None:
    """Independent judge (another model family) on the verified summaries: a text is
    published only if it passes; a rejected one goes to derived/texts_review/."""
    from synaptica.llm import LLM, QuotaExhausted
    from synaptica.narrative import pipeline

    if provider is None:
        typer.echo("No --provider given: nothing judged.")
        raise typer.Exit(0)
    name = model or DEFAULT_JUDGE_MODELS.get(provider)
    if name is None:
        typer.echo(f"No default judge for {provider}: pass --model.", err=True)
        raise typer.Exit(1)
    studies = _narrative_studies(study)
    try:
        result = pipeline.run_judge(LLM(provider, name), studies, limit=limit, until=_until(until))
    except QuotaExhausted as exc:
        typer.echo(f"LLM quota used up: {exc}; the rest waits for the next run", err=True)
        raise typer.Exit(0) from exc
    except ValueError as exc:  # same family as the writer
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(_outcomes("Judged", result))


@app.command()
def weekly(
    provider: ProviderOption = None,
    model: ModelOption = None,
    judge_model: Annotated[
        str | None, typer.Option(help="Judge model (default per provider, D4).")
    ] = None,
    week: Annotated[
        str | None, typer.Option(help="ISO week such as 2026-W45 (default: last week).")
    ] = None,
) -> None:
    """Weekly summary of the studies whose summaries were published that week: same
    chain, checks and judge -> derived/weekly/ (or weekly_review/, with the fallback)."""
    from synaptica.llm import LLM, QuotaExhausted
    from synaptica.narrative import weekly as weekly_mod
    from synaptica.news import classify
    from synaptica.store import utc_today

    llm = _llm(provider, model)
    if llm is None:
        typer.echo("No --provider given: nothing written.")
        raise typer.Exit(0)
    judge_name = judge_model or DEFAULT_JUDGE_MODELS.get(provider)
    if judge_name is None:
        typer.echo(f"No default judge for {provider}: pass --judge-model.", err=True)
        raise typer.Exit(1)
    if not classify.warehouse_path().exists():
        typer.echo("No warehouse yet: run `syn build` first.", err=True)
        raise typer.Exit(1)
    key = week or weekly_mod.last_week(utc_today())
    chosen = weekly_mod.choose(weekly_mod.candidates(key))
    if weekly_mod.is_up_to_date(key, chosen):
        typer.echo(f"Weekly summary {key}: up to date ({len(chosen)} studies)")
        raise typer.Exit(0)
    try:
        status = weekly_mod.write_weekly(llm, LLM(provider, judge_name), key, chosen)
    except QuotaExhausted as exc:
        typer.echo(f"LLM quota used up: {exc}; the weekly summary waits", err=True)
        raise typer.Exit(0) from exc
    except ValueError as exc:  # judge of the writer's family
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Weekly summary {key}: {status} ({len(chosen)} studies)")


@app.command()
def build(
    as_of: Annotated[
        str | None, typer.Option(help="Pin 'today' (YYYY-MM-DD) for date-based tests (CI).")
    ] = None,
) -> None:
    """Rebuild the warehouse: ``dbt build`` (models and tests) on data/raw/."""
    dbt_dir = config.project_root() / "dbt"
    env = {**os.environ, "SYN_DATA_DIR": str(config.get_paths().data)}
    # --full-refresh: the warehouse is rebuilt from data/ on every run (D1), so a seed whose
    # columns changed is recreated instead of loaded into the old table.
    cmd = ["dbt", "build", "--full-refresh", "--project-dir", str(dbt_dir),
           "--profiles-dir", str(dbt_dir)]  # fmt: skip
    if as_of:
        cmd += ["--vars", f"{{as_of: '{as_of}'}}"]
    raise typer.Exit(subprocess.run(cmd, env=env, check=False).returncode)


@app.command()
def site(
    out: Annotated[str | None, typer.Option(help="Output folder [default: site/_build].")] = None,
    check: Annotated[
        bool, typer.Option("--check", help="Only check the built site (links, hreflang…).")
    ] = False,
) -> None:
    """Render the static website (ES + EN), or check it (adapted from paleo-atlas)."""
    out_dir = Path(out) if out else config.project_root() / "site" / "_build"
    if check:
        from synaptica.site.check import check_site

        result = check_site(out_dir)
        for problem in result.problems[:50]:
            typer.echo(f"  {problem}")
        typer.echo(f"Checked {result.pages} pages: {len(result.problems)} problems")
        raise typer.Exit(0 if result.passed else 1)
    from synaptica.site.build import build_site

    try:
        built = build_site(out_dir, data_dir=config.get_paths().data)
    except RuntimeError as exc:  # a folder `syn site` did not create
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Site: {built['pages']} pages ({', '.join(built['kinds'])}) → {out_dir}")


@app.command()
def check() -> None:
    """Exit 0 if any source has something new, 1 if nothing changed and 2 if the check
    itself failed (adapted from paleo-atlas, its ADR D10). On 2 the workflow runs
    everything, so the error surfaces in the ingestion and the run report instead of
    passing for "no changes" (a lesson from Paleo)."""
    import httpx

    from synaptica.http import HttpError, make_client
    from synaptica.ingest import biorxiv, crossref, europepmc, journals, news, pubmed

    changed = []
    try:
        with make_client() as client:
            if pubmed.has_new_records(client):
                changed.append("pubmed")
            if crossref.has_new_notices(client):
                changed.append("crossref")
            if europepmc.has_new_records(client):
                changed.append("europepmc")
            if biorxiv.has_new_preprints(client):
                changed.append("biorxiv")
            if journals.has_new_items(client):
                changed.append("journals")
            if news.has_new_items(client):
                changed.append("news")
    except (HttpError, httpx.HTTPError) as exc:
        typer.echo(f"check failed: {exc}", err=True)
        raise typer.Exit(2) from exc
    if changed:
        typer.echo("changed: " + ", ".join(changed))
        raise typer.Exit(0)
    typer.echo("no changes")
    raise typer.Exit(1)


# --- review queue (plan, step R; ADR 0005) -------------------------------------------------

QueueOption = Annotated[Path, typer.Option(help="Review queue (JSON) the page shows.")]


def _review_dir() -> Path:
    """Her decision log: ``review/`` in the data folder (the data branch, from step 28)."""
    return config.get_paths().data / "review"


@review_app.command("queue")
def review_queue(
    out: Annotated[Path, typer.Option(help="Write the queue (JSON) here.")],
    today: Annotated[str | None, typer.Option(help="Day (ISO, UTC); default today.")] = None,
    run: Annotated[
        list[Path] | None,
        typer.Option(help="Also a past run's texts (its derived/ and summary.json); repeatable."),
    ] = None,
) -> None:
    """Today's queue: every source of items, minus what she decided, capped (40 on a
    weekday, 10 at the weekend). Then ``syn review page --queue`` on the same file."""
    import datetime as dt

    from synaptica.review.collect import collect, run_spot_checks

    paths = config.get_paths()
    day = dt.date.fromisoformat(today) if today else dt.datetime.now(dt.UTC).date()
    extra = [item for r in run or [] for item in run_spot_checks(r)]
    q = collect(paths.data / "warehouse.duckdb", paths.derived, _review_dir(), day, extra)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(q.model_dump_json(indent=1) + "\n", encoding="utf-8")
    held = sum(bool(i.warnings) for i in q.items)
    typer.echo(f"queue: {len(q.items)} items ({held} held edits) -> {out}")


@review_app.command("page")
def review_page(
    queue: QueueOption,
    out: Annotated[Path, typer.Option(help="Folder for the pages.")],
    label: Annotated[str, typer.Option(help="Round label, in the file names.")] = "",
) -> None:
    """Her two review pages (public, and private for Neuro Diseases) from a queue."""
    from synaptica.review.models import Queue
    from synaptica.review.page import OUT, page_items, render

    q = Queue.model_validate_json(queue.read_text("utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    for variant, default in OUT.items():
        items = page_items(q, variant)
        if not items:
            continue  # no empty page to send her
        name = f"{default.stem}-{label}{default.suffix}" if label else default.name
        (out / name).write_text(render(q, variant, label), encoding="utf-8")
        typer.echo(f"{variant}: {len(items)} items -> {out / name}")


@review_app.command("round")
def review_round(
    queue: QueueOption, out: Annotated[Path, typer.Option(help="Folder of the round.")]
) -> None:
    """Next round: apply her log to the queue and write what still waits for her."""
    from synaptica.review.apply import publishable
    from synaptica.review.models import Queue
    from synaptica.review.rounds import round_pages

    q = Queue.model_validate_json(queue.read_text("utf-8"))
    waiting, sts = round_pages(q, _review_dir(), out)
    published = sum(publishable(st) for st in sts.values())
    typer.echo(f"waiting: {len(waiting.items)} · publishable: {published} -> {out}")


@review_app.command("intake")
def review_intake(
    event: Annotated[Path, typer.Option(help="The GitHub `issues` event (JSON).")],
    queue: QueueOption,
    reviewer: Annotated[str, typer.Option(help="Her GitHub login (a repository variable).")],
    reply: Annotated[Path, typer.Option(help="Write the reply for the Issue here.")],
    cache_root: Annotated[Path | None, typer.Option(help="Abstract cache.")] = None,
    efetch: Annotated[
        list[Path] | None,
        typer.Option(help="PubMed efetch XML for abstracts not in the cache; repeatable."),
    ] = None,
) -> None:
    """Read one of her Issues: applied, held (back to her queue) or refused; exit 2 when an
    edited text has no source to check it against (the Issue waits)."""
    import json

    from synaptica.review.intake import run

    result = run(event, queue, _review_dir(), reviewer, reply, cache_root=cache_root, efetch=efetch)
    typer.echo(json.dumps(result))
    if result["status"] == "error":
        raise typer.Exit(2)
