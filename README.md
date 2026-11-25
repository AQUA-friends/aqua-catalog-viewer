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
validation problems are errors (`strict`), the AQUA engines offered for `gsv` sources, the
`blob_url` used for "view file" links, and optional per-repo `descriptions` (catalog name → one
sentence shown on the homepage card; unknown names only produce a warning).

## Machines (`metadata.machine`)

A source, experiment or model may set `metadata.machine` to a name or a list of names (the nearest
one up the tree wins; matching `machine.yaml` is case-insensitive). When present it replaces the
automatic list (machines of `machine.yaml` that set the catalog variables) and the "may not be
synced" warning. Machines not described in `machine.yaml` use the catalog defaults in their intake
snippet. For `gsv`/`z3fdb` the declared machines are shown (local access) and `polytope` gets the
`online` badge. For other drivers `online` appears when the path or its defaults are remote URLs,
and it is the preselected machine unless the visitor chose another one before.

## Publish

### GitHub Actions (`.github/workflows/pages.yml`)

Runs every Monday and on demand (Actions tab → "Build and deploy site" → Run workflow, or
`gh workflow run pages.yml`). It runs the tests, clones the repos of `site.yaml` into `repos/`
(`python -m viewer.fetch`), builds with `--repos-dir repos` and deploys with `actions/deploy-pages`.
In Settings → Pages the source must be "GitHub Actions".

The evaluation catalog is on a private GitLab, so the workflow needs two repository secrets,
`GITLAB_USER` and `GITLAB_TOKEN`: a GitLab project **deploy token** with only the `read_repository`
scope (it has its own user name), or a project access token (Reporter, `read_repository`).
Set them without echoing the token:

```bash
gh secret set GITLAB_USER --repo AQUA-friends/aqua-catalog-viewer
gh secret set GITLAB_TOKEN --repo AQUA-friends/aqua-catalog-viewer   # paste the token at the prompt
```

An expiring token makes the scheduled run fail at "Fetch catalog repos"; create a new one and
re-run `gh secret set GITLAB_TOKEN`.

There is no manual deploy path: Pages only serves what this workflow uploads. To check a change
before pushing, build locally (see above).

## Next

- Rebuild when a catalog repo changes (a `repository_dispatch` from Climate-DT-catalog), not only weekly.
- Optional: by-source page, password gate.
