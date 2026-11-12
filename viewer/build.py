"""Render the loaded catalog tree to static HTML.

    python -m viewer.build [--config site.yaml] [--out public]

All links are relative, so the site works under any base path (GitHub Pages
project sites live under /<repo>/) and from file://.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .load import load_site, walk
from .snippets import fmt_date, leaf_tabs

HERE = Path(__file__).parent
LEVTYPES = {"sfc": "surface", "sol": "soil", "pl": "pressure levels", "o2d": "ocean 2D",
            "o3d": "ocean 3D", "ml": "model levels", "hl": "height levels"}
NODE_CHIPS = [("exp", "expid"), ("atm", "resolution_atm"), ("oce", "resolution_oce"),
              ("forcing", "forcing"), ("start", "start")]


def slug(s):
    return re.sub(r"[^\w.-]", "_", str(s))


def clean(text):
    """Descriptions are sometimes quoted twice in the YAML: '"text"'."""
    return str(text).strip().strip("\"'") if text else ""


def git_commit(path):
    try:
        out = subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def period(info):
    if "start" not in info and "end" not in info:
        return ""
    return f"{fmt_date(info.get('start', '?'))} → {fmt_date(info.get('end', '?'))}"


class Builder:
    def __init__(self, cfg, site, out):
        self.cfg, self.site, self.out = cfg, site, Path(out)
        self.engines = cfg.get("engines") or ["gsv"]
        self.search, self.paths = [], set()
        self.env = Environment(loader=FileSystemLoader(HERE / "templates"),
                               autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
        self.env.filters["clean"] = clean
        self.env.filters["date"] = fmt_date
        self.env.globals.update(
            site_title=site["title"], levtypes=LEVTYPES, engine_docs_url=cfg.get("engine_docs_url") or "",
            generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    # -- output ----------------------------------------------------------
    def write(self, rel, template, **ctx):
        if rel in self.paths:
            raise SystemExit(f"two pages map to {rel}: catalog or entry names collide")
        self.paths.add(rel)
        root = "../" * rel.count("/")
        html = self.env.get_template(template).render(root=root, **ctx)
        target = self.out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html)

    # -- views -----------------------------------------------------------
    def counts(self, entries):
        leaves = [e for _, e in walk(entries) if e["kind"] != "node"]
        return len(leaves), Counter(str(e["driver"]) for e in leaves if e["kind"] == "source")

    def node_view(self, e, url):
        n, drivers = self.counts(e.get("children", []))
        meta = e["metadata"]
        return {"name": e["name"], "url": url, "description": clean(e["description"]),
                "chips": [(k, meta[m]) for k, m in NODE_CHIPS if meta.get(m) not in (None, "")],
                "n_sources": n, "drivers": sorted(drivers)}

    def row_view(self, e, url):
        i = e["info"]
        return {"name": e["name"], "url": url, "description": clean(e["description"]), "driver": e["driver"],
                "grid": i.get("grid", ""), "levtype": i.get("levtype", ""), "period": period(i),
                "fixer": i.get("fixer", "")}

    # -- pages -----------------------------------------------------------
    def build_level(self, rcfg, cat, entries, trail, crumbs, parent=None):
        base = "/".join(slug(x) for x in [cat["name"], *trail])
        nodes, rows = [], []
        for e in entries:
            etrail = trail + [e["name"]]
            epath = "/".join(slug(x) for x in [cat["name"], *etrail])
            url = f"{epath}/index.html"
            here = crumbs + [(e["name"], url)]
            if e["kind"] == "node":
                nodes.append(self.node_view(e, url))
                self.search.append({"t": " / ".join([cat["name"], *etrail]), "u": url,
                                    "d": clean(e["description"]), "k": "node"})
                self.build_level(rcfg, cat, e["children"], etrail, here, e)
            else:
                rows.append(self.row_view(e, url))
                self.build_leaf(rcfg, cat, e, url, crumbs)
        meta = (parent or {}).get("metadata", {})
        note = (meta.get("dashboard") or {}).get("note") if isinstance(meta.get("dashboard"), dict) else None
        readme = None
        if not trail and cat.get("readme"):
            readme = markdown.markdown(cat["readme"], extensions=["tables", "fenced_code"])
        self.write(f"{base}/index.html", "node.html", crumbs=crumbs, title=(trail or [cat["name"]])[-1],
                   description=clean((parent or {}).get("description")),
                   chips=[(k, meta[m]) for k, m in NODE_CHIPS if meta.get(m) not in (None, "")],
                   note=note, nodes=nodes, rows=rows, readme=readme,
                   n_sources=self.counts(entries)[0])

    def build_leaf(self, rcfg, cat, leaf, url, crumbs):
        rel = Path(leaf["source_file"]).relative_to(Path(rcfg["path"]).expanduser())
        blob = f"{rcfg['blob_url']}/{rel}" if rcfg.get("blob_url") else None
        info = leaf.get("info", {})
        full = " / ".join([cat["name"], *leaf["trail"]])
        self.search.append({"t": full, "u": url, "d": clean(leaf["description"]), "k": leaf["driver"] or "placeholder",
                            "g": info.get("grid", "")})
        self.write(url, "source.html", crumbs=crumbs, leaf=leaf, info=info, period=period(info),
                   title=leaf["name"], tabs=leaf_tabs(rcfg["name"], cat["name"], leaf, self.engines),
                   blob=blob, source_rel=str(rel))

    def build_home(self):
        repos = []
        for repo, rcfg in zip(self.site["repos"], self.cfg["repos"]):
            cats = []
            for cat in repo["catalogs"]:
                nodes = list(walk(cat["children"]))
                n, drivers = self.counts(cat["children"])
                cats.append({"name": cat["name"], "url": f"{slug(cat['name'])}/index.html",
                             "models": sum(1 for d, e in nodes if d == 1 and e["kind"] == "node"),
                             "experiments": sum(1 for d, e in nodes if d == 2 and e["kind"] == "node"),
                             "sources": n, "drivers": sorted(drivers)})
            repos.append({"name": repo["name"], "commit": git_commit(Path(rcfg["path"]).expanduser()),
                          "url": (rcfg.get("blob_url") or "").rsplit("/blob/", 1)[0].rsplit("/-", 1)[0],
                          "catalogs": cats})
        self.write("index.html", "home.html", crumbs=[], repos=repos)

    def run(self):
        if self.out.exists():
            shutil.rmtree(self.out)
        seen = {}
        for repo in self.site["repos"]:
            for cat in repo["catalogs"]:
                if cat["name"] in seen:
                    raise SystemExit(f"catalog `{cat['name']}` exists in both {seen[cat['name']]} and {repo['name']}")
                seen[cat["name"]] = repo["name"]
        rcfgs = {r["name"]: r for r in self.cfg["repos"]}
        for repo in self.site["repos"]:
            for cat in repo["catalogs"]:
                self.build_level(rcfgs[repo["name"]], cat, cat["children"], [], [(cat["name"], f"{slug(cat['name'])}/index.html")])
        self.build_home()
        shutil.copytree(HERE / "static", self.out / "static")
        (self.out / "search.json").write_text(json.dumps(self.search, separators=(",", ":")))
        (self.out / ".nojekyll").write_text("")
        return len(self.paths)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="site.yaml")
    ap.add_argument("--out", default="public")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(args.config).read_text())
    site = load_site(args.config)
    errors = [p for p in site["problems"] if p["level"] == "error"]
    for p in site["problems"]:
        print(f"{p['level'].upper():7} [{p['repo']}] {p['where']}: {p['msg']}", file=sys.stderr)
    if errors:
        print(f"{len(errors)} error(s): not building", file=sys.stderr)
        return 1
    pages = Builder(cfg, site, args.out).run()
    print(f"built {pages} pages into {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
