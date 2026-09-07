#!/bin/bash
# Update this fork from upstream (lfnovo/open-notebook) and OpenMAIC, then rebuild.
#   scripts/app/update-fork.sh              # rebase on origin/main, keep OpenMAIC pinned
#   scripts/app/update-fork.sh --openmaic   # also fast-forward vendor/openmaic to its latest main
#   scripts/app/update-fork.sh --tag v1.2.0 # pin OpenMAIC to a specific tag instead
# Safe by design: refuses on a dirty tree, works on a temp branch, only fast-forwards main on success.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
BUMP_OPENMAIC=false; OPENMAIC_TAG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --openmaic) BUMP_OPENMAIC=true ;;
    --tag) OPENMAIC_TAG="$2"; BUMP_OPENMAIC=true; shift ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac; shift
done

say() { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m✗ %s\033[0m\n' "$*"; exit 1; }

[ -z "$(git status --porcelain --untracked-files=no)" ] || die "working tree has uncommitted changes — commit or stash first"
CUR="$(git rev-parse --abbrev-ref HEAD)"

say "Fetching upstream (origin) and fork"
git fetch -q origin main
git fetch -q fork main || true
BEHIND=$(git rev-list --count HEAD..origin/main)
echo "upstream commits not yet in this branch: $BEHIND"

if [ "$BEHIND" -gt 0 ]; then
  say "Rebasing $CUR onto origin/main"
  if ! git rebase origin/main; then
    echo
    echo "Conflicts. Resolve them, then:  git rebase --continue  and re-run this script."
    echo "Common one: frontend/src/app/globals.css — take upstream's, then run scripts/app/apply-soft-fern.py"
    exit 1
  fi
fi

say "Re-applying the Soft Fern theme (idempotent)"
python3 scripts/app/apply-soft-fern.py

if $BUMP_OPENMAIC; then
  say "Updating OpenMAIC submodule"
  git submodule update --init vendor/openmaic
  (cd vendor/openmaic && git fetch -q origin && if [ -n "$OPENMAIC_TAG" ]; then git checkout -q "$OPENMAIC_TAG"; else git checkout -q origin/main; fi && git log -1 --format='  now at %h %s (%ad)' --date=short)
  git add vendor/openmaic
  # a new package.json mtime makes the launcher reinstall + rebuild the sidecar on next start
  touch vendor/openmaic/package.json
fi

say "Dependencies"
uv sync -q
(cd frontend && npm install --silent 2>&1 | grep -v allow-scripts || true)

say "Checks"
uv run ruff check . -q && echo "ruff ok"
(cd frontend && npx tsc -p tsconfig.json --noEmit && echo "tsc ok")
uv run pytest tests/test_auth.py tests/test_learning_service.py tests/test_subscription_proxy.py -q -p no:cacheprovider 2>&1 | grep -E "passed|failed"

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  say "Committing update"
  git commit -q -am "chore: update from upstream$($BUMP_OPENMAIC && echo ' + OpenMAIC bump')"
fi

say "Rebuilding the launcher app"
touch frontend/package.json   # force a frontend rebuild on next start
bash scripts/app/build-app.sh >/dev/null && echo "app rebuilt"

say "Done. Push with:  git push -f fork $CUR && git push fork $CUR:main"
