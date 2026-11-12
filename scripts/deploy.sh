#!/usr/bin/env bash
# Build the site and publish it to the gh-pages branch of `origin`.
# Manual stage-1 deploy: GitHub Pages serves the gh-pages branch (root).
# Replace with a GitHub Actions workflow later (see README, "Next").
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"

python="${PYTHON:-.venv/bin/python}"
"$python" -m viewer.build --out public

remote="$(git remote get-url origin)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

cp -R public/. "$tmp"
cd "$tmp"
git init -q -b gh-pages
git add -A
git commit -q -m "Deploy site $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push --force "$remote" gh-pages
echo "Pushed gh-pages. Site: https://aqua-friends.github.io/aqua-catalog-viewer/"
