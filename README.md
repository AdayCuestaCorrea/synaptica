**English** · [Español](README.es.md)

# SYNAPTICA — your Neuroscience hub

A free neuroscience website in Spanish and English that updates itself every day: science news with verified summaries, and sections to learn how the brain works. By Aday Cuesta Correa (development) and Sofía (scientific review).

**Website:** https://adaycuestacorrea.github.io/synaptica/ (Spanish and English, light and dark).

**Status:** Phase 1 (the base) is built and running: Neuro News updates itself every day since 2026-11-13. The phase closes after 14 days of daily runs without intervention. The plan and its order live in [`SCOPE.md`](SCOPE.md) (Spanish, canonical).

## How a day works

A GitHub Actions workflow runs every morning ([`pipeline.yml`](.github/workflows/pipeline.yml)):

1. **Ingest** new records from PubMed, Crossref (retractions and corrections), Europe PMC, bioRxiv and medRxiv, the Nature · Science · Cell feeds, three science news outlets and OpenAlex. Only metadata goes to git; abstracts stay in a private cache.
2. **Classify and summarize** with free LLMs on Groq: each study gets a type, verified facts, an English summary and a Spanish adaptation. Every sentence cites its facts, numbers and names must match the source, no run of 8 words may be copied, and a judge model of another family must pass it. Anything that fails shows a fallback text built from the data only.
3. **Rebuild** the DuckDB warehouse with dbt (tests included) and the static site, with `syn site --check` (links, hreflang, medical notice on every page, signals on every study).
4. **Review:** a sample of the summaries goes to a page where the neuroscientist approves, corrects or rejects them from her browser; her decisions come back as GitHub Issues and are applied automatically.
5. **Commit** the data to the `data` branch and publish on GitHub Pages; once a week the marts are mirrored to the BigQuery sandbox.

## What it is and will be

- **Neuro News** every day from open sources (PubMed, Europe PMC, bioRxiv, Nature · Science · Cell metadata, science news outlets), each summary checked against its source before it is published.
- **Neuro Atlas** (human and rat brain in 3D), **Neuro Lab**, **Neuro Glossary**, **Neuro Learn**, **Neuro Diseases**, **Neuro History** and **Neuro Experiments**.
- **Not medical advice.** Health content is reviewed by a neuroscientist before it is published.
- **0 € a month:** GitHub Actions, GitHub Pages, free API tiers and local models.

It reuses the engine of [Paleo Atlas](https://github.com/AdayCuestaCorrea/paleo-atlas): state in git, warehouse rebuilt on every run, one command per step, and LLM texts that cite their sources and pass automatic checks.

## Run it locally

```sh
uv sync
uv run syn --help
uv run syn doctor          # checks the environment
uv run pytest              # tests, never use the network
uv run ruff check . && uv run ruff format --check .
```

## Documentation (Spanish)

- [`SCOPE.md`](SCOPE.md): scope, phases, decisions and change log.
- [`docs/propuesta.md`](docs/propuesta.md): the product as approved.
- [`docs/adr/`](docs/adr/README.md): architecture decision records.
- [`docs/fases/`](docs/fases/README.md): one document per finished phase.

## License

Code: [AGPL-3.0](LICENSE) · Original texts: [CC BY-SA 4.0](LICENSE-CONTENT.md) · Third-party data, images and 3D models keep their own licenses.
