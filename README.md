**English** · [Español](README.es.md)

# SYNAPTICA — your Neuroscience hub

A free neuroscience website in Spanish and English that updates itself every day: science news with verified summaries, and sections to learn how the brain works. By Aday Cuesta Correa (development) and Sofía (scientific review).

**Status:** Phase 0 (foundations). There is no website yet. The plan and its order live in [`SCOPE.md`](SCOPE.md) (Spanish, canonical).

## What it will be

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
