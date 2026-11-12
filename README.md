# aqua-catalog-viewer

A static website to browse intake/AQUA catalogs (catalog → model → experiment → source) and copy
the code that opens a source with AQUA or plain intake. Live at
<https://aqua-friends.github.io/aqua-catalog-viewer/>.

The generator reads the catalog YAML files directly (no intake, no data access) and writes plain HTML.
All links are relative, so the site works under any base path.

## Build locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m viewer.build           # writes public/
python3 -m http.server -d public 8000      # preview at http://localhost:8000
.venv/bin/python -m viewer.load --stats    # counts per catalog + validation problems
.venv/bin/python -m unittest discover -s tests -t .
```

## Configure

`site.yaml` lists the repos to read (local paths), which catalogs to include or exclude, whether
validation problems are errors (`strict`), the AQUA engines offered for `gsv` sources, and the
`blob_url` used for "view file" links.

## Publish (manual, for now)

```bash
scripts/deploy.sh
```

It builds the site and force-pushes it to the `gh-pages` branch; GitHub Pages serves that branch.
`gh-pages` is generated output, never edit it by hand.

## Next

- Replace the manual deploy by a GitHub Actions workflow (checkout the catalog repos, build, deploy
  with `actions/deploy-pages`), on a schedule and on demand. The GitLab evaluation repo needs a
  read-only token stored as an Actions secret.
- Optional: by-source page, per-machine paths, password gate.
