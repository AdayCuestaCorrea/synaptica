#!/usr/bin/env bash
# Commit and push what changed in the checkout of the data branch (the current directory),
# for pipeline.yml. Usage:
#   commit_data.sh final               everything, at the end of the run
#   commit_data.sh checkpoint <stage>  what an LLM stage produced, between stages (v145)
#
# Checkpoints exist because a run can be cut hard (run 43609191046, 2026-11-14: cancelled
# after 45 minutes of Groq work; not even the always() steps ran, so 847 decisions were
# lost). The LLM commands save their progress to derived/ batch by batch; pushing it
# between stages keeps what was done. A checkpoint leaves out runs/: the run record is
# completed and committed at the end.
set -euo pipefail

mode=${1:?final or checkpoint}
if [ "$mode" = checkpoint ]; then
  git add -A -- . ':!runs'
else
  git add -A
fi
if git diff --cached --name-only | grep -E '(^|/)cache/|\.duckdb'; then
  echo "::error::private or local files staged; refusing to commit"
  exit 1
fi
if git diff --cached --quiet; then
  echo "No data changes."
  exit 0
fi

day=$(date -u +%F)
if [ "$mode" = checkpoint ]; then
  message="Checkpoint $day: ${2:?stage name}"
elif [ -z "$(git diff --cached --name-only | grep -v '^runs/' || true)" ]; then
  message="Run log $day"
else
  message="Data update $day"
fi
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -q -m "$message"
git pull -q --rebase origin data
git push -q origin HEAD:data
echo "$message"
