#!/usr/bin/env bash
# The checks of .github/workflows/ci.yml, run locally before a push, so work does not wait
# on GitHub Actions (Aday's option A, SCOPE v195). With a rebuilt warehouse of the data
# branch (DATA_DIR=path), it also builds and checks the site on real data, as the daily run
# will. No network: fixtures only, like the CI.
#
#   scripts/ci_local.sh                 # what the CI runs
#   DATA_DIR=/path/to/data scripts/ci_local.sh   # … plus syn site --check on real data
set -euo pipefail
cd "$(dirname "$0")/.."
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
SYN_DATA_DIR="$tmp/data" uv run syn doctor
SYN_DATA_DIR="$tmp/data" uv run python scripts/seed_fixture_data.py
SYN_DATA_DIR="$tmp/data" uv run syn build --as-of 2026-11-09
SYN_DATA_DIR="$tmp/data" uv run syn site --out "$tmp/site"
uv run syn site --check --out "$tmp/site"
if [ -n "${DATA_DIR:-}" ]; then
  [ -f "$DATA_DIR/warehouse.duckdb" ] || { echo "No warehouse in $DATA_DIR: syn build first"; exit 1; }
  SYN_DATA_DIR="$DATA_DIR" uv run syn site --out "$tmp/site-real"
  uv run syn site --check --out "$tmp/site-real"
fi
echo "ci_local: all green"
