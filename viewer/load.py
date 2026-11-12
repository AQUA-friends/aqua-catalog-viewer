"""Load intake catalog repos into one normalized, JSON-serializable tree.

Structure produced (see load_site):

    site = {title, repos: [{name, catalogs: [catalog]}], problems: [...]}
    catalog = {name, readme, children: [entry]}
    entry   = node  {kind: "node", name, description, metadata, children, ...}
            | leaf  {kind: "source"|"placeholder", name, driver, args, info, ...}

The YAML is parsed directly (no intake import, no data access). A source whose
driver is `yaml_file_cat` is a node: its `args.path` is followed recursively, so
the depth of the tree is whatever the catalog defines.

CLI:  python -m viewer.load [--config site.yaml] [--stats] [--dump out.json]
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

CATALOG_DIR = re.compile(r"\{\{\s*CATALOG_DIR\s*\}\}")
MAX_DEPTH = 8


class Loader:
    def __init__(self, repo, strict):
        self.repo = repo
        self.strict = strict
        self.problems = []

    # -- problems ---------------------------------------------------------
    def problem(self, where, msg, hard=False):
        """Hard problems (unreadable files, bad config) always fail the build;
        validation problems fail it only for strict repos."""
        level = "error" if hard or self.strict else "warning"
        self.problems.append({"level": level, "repo": self.repo, "where": str(where), "msg": msg})

    def read_yaml(self, path):
        try:
            data = yaml.safe_load(Path(path).read_text())
        except (OSError, yaml.YAMLError) as e:
            self.problem(path, f"cannot read YAML: {str(e).splitlines()[0]}", hard=True)
            return {}
        if data is None:
            return {}
        if not isinstance(data, dict):
            self.problem(path, "top level is not a mapping", hard=True)
            return {}
        return data

    # -- tree -------------------------------------------------------------
    def load_file(self, path, trail, seen):
        """Entries listed under `sources:` of one catalog file."""
        if path in seen or len(trail) > MAX_DEPTH:
            self.problem(path, "catalog cycle or nesting too deep", hard=True)
            return []
        data = self.read_yaml(path)
        sources = data.get("sources") or {}
        if not isinstance(sources, dict):
            self.problem(path, "`sources` is not a mapping", hard=True)
            return []
        return [
            self.entry(name, spec if isinstance(spec, dict) else {}, path, trail + [name], seen | {path})
            for name, spec in sources.items()
        ]

    def entry(self, name, spec, path, trail, seen):
        where = f"{path} :: {'/'.join(trail)}"
        driver = spec.get("driver")
        args = spec.get("args") or {}
        out = {
            "name": name,
            "trail": trail,
            "description": spec.get("description"),
            "metadata": spec.get("metadata") or {},
            "driver": driver,
            "source_file": str(path),
        }
        if "driver" not in spec:
            self.problem(where, "source has no `driver`")

        if driver == "yaml_file_cat":
            out["kind"] = "node"
            out["children"] = self.follow(args.get("path"), path, where, trail, seen)
            return out

        out["kind"] = "placeholder" if driver is None else "source"
        out["args"] = args
        out["parameters"] = spec.get("parameters") or {}
        out["info"] = source_info(spec)
        self.validate_leaf(out, where)
        return out

    def follow(self, target, path, where, trail, seen):
        if not isinstance(target, str):
            self.problem(where, "yaml_file_cat without `args.path`")
            return []
        here = Path(path).parent
        if CATALOG_DIR.search(target):
            target = Path(CATALOG_DIR.sub(str(here), target))  # already rooted at this file's folder
        else:
            target = here / target  # plain relative path (a no-op for absolute ones)
        if "{{" in str(target):
            self.problem(where, f"unresolved template in path: {target}", hard=True)
            return []
        if not target.exists():
            self.problem(where, f"referenced file not found: {target}", hard=True)
            return []
        return self.load_file(target, trail, seen)

    # -- validation (per driver) -------------------------------------------
    def validate_leaf(self, leaf, where):
        driver, args = leaf["driver"], leaf["args"]
        if driver == "gsv" and not isinstance(args.get("request"), dict):
            self.problem(where, "gsv source without `args.request`")
        if driver in ("zarr", "netcdf") and not args.get("urlpath"):
            self.problem(where, f"{driver} source without `args.urlpath`")
        for pname, p in leaf["parameters"].items():
            if not isinstance(p, dict):
                continue
            allowed, default = p.get("allowed"), p.get("default")
            if allowed is not None and default is not None and default not in allowed:
                self.problem(where, f"parameter `{pname}` default {default!r} not in allowed {allowed}")


def source_info(spec):
    """The few fields worth showing on a source page, pulled from known places."""
    args = spec.get("args") or {}
    meta = spec.get("metadata") or {}
    req = args.get("request") if isinstance(args.get("request"), dict) else {}

    def text(v):
        return None if v is None else str(v)

    info = {
        "fixer": meta.get("fixer_name"),
        "grid": meta.get("source_grid_name"),
        "start": text(args.get("data_start_date")),
        "end": text(args.get("data_end_date")),
        "bridge_start": text(args.get("bridge_start_date")),
        "savefreq": args.get("savefreq"),
        "timestep": args.get("timestep"),
        "variables": meta.get("variables"),
        "levtype": req.get("levtype"),
        "levels": req.get("levelist", meta.get("levels")),
    }
    return {k: v for k, v in info.items() if v is not None}


def load_catalog(loader, cdir):
    cat_file = cdir / "catalog.yaml"
    if not cat_file.exists():
        loader.problem(cdir, "no catalog.yaml", hard=True)
        return None
    readme = cdir / "README.md"
    return {
        "name": cdir.name,
        "readme": readme.read_text() if readme.exists() else None,
        "children": loader.load_file(cat_file, [], set()),
    }


def repo_path(cfg, repos_dir=None):
    """Where a repo lives: <repos_dir>/<name> when a repos dir is given (CI), else its `path`."""
    if repos_dir:
        return Path(repos_dir) / cfg["name"]
    return Path(cfg["path"]).expanduser()


def load_repo(cfg, repos_dir=None):
    name = cfg["name"]
    loader = Loader(name, bool(cfg.get("strict", False)))
    root = repo_path(cfg, repos_dir) / "catalogs"
    if not root.is_dir():
        loader.problem(root, "no catalogs/ directory", hard=True)
        return {"name": name, "catalogs": []}, loader.problems

    available = sorted(p.name for p in root.iterdir() if p.is_dir())
    include = cfg.get("include")
    if include:
        for missing in sorted(set(include) - set(available)):
            loader.problem(root, f"included catalog `{missing}` does not exist (have: {', '.join(available)})", hard=True)
        wanted = [c for c in available if c in include]
    else:
        wanted = available
    wanted = [c for c in wanted if c not in (cfg.get("exclude") or [])]

    catalogs = [c for c in (load_catalog(loader, root / n) for n in wanted) if c]
    return {"name": name, "catalogs": catalogs}, loader.problems


def load_site(config_path, repos_dir=None):
    cfg = yaml.safe_load(Path(config_path).read_text())
    repos, problems = [], []
    for repo_cfg in cfg["repos"]:
        repo, probs = load_repo(repo_cfg, repos_dir)
        repos.append(repo)
        problems += probs
    return {"title": cfg.get("title", "Catalog viewer"), "repos": repos, "problems": problems}


# -- helpers for callers --------------------------------------------------
def walk(entries, depth=1):
    """Yield (depth, entry) for every entry below `entries`, depth-first."""
    for e in entries:
        yield depth, e
        yield from walk(e.get("children", []), depth + 1)


def stats(site):
    lines = []
    total = Counter()
    for repo in site["repos"]:
        lines.append(f"== {repo['name']}")
        for cat in repo["catalogs"]:
            entries = list(walk(cat["children"]))
            nodes_by_depth = Counter(d for d, e in entries if e["kind"] == "node")
            leaves = [e for _, e in entries if e["kind"] != "node"]
            drivers = Counter(str(e["driver"]) for e in leaves)
            total.update(drivers)
            levels = ", ".join(f"L{d}:{n}" for d, n in sorted(nodes_by_depth.items()))
            lines.append(
                f"  {cat['name']:28} nodes[{levels}] sources={len(leaves)} "
                + " ".join(f"{k}={v}" for k, v in sorted(drivers.items()))
            )
    lines.append(f"== total sources: {sum(total.values())}  " + " ".join(f"{k}={v}" for k, v in sorted(total.items())))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="site.yaml")
    ap.add_argument("--repos-dir", help="read repos from <dir>/<name> instead of their `path`")
    ap.add_argument("--stats", action="store_true", help="print counts per catalog")
    ap.add_argument("--dump", metavar="FILE", help="write the normalized tree as JSON")
    args = ap.parse_args(argv)

    site = load_site(args.config, args.repos_dir)
    if args.stats:
        print(stats(site))
    if args.dump:
        Path(args.dump).write_text(json.dumps(site, indent=1, default=str))

    errors = [p for p in site["problems"] if p["level"] == "error"]
    for p in site["problems"]:
        print(f"{p['level'].upper():7} [{p['repo']}] {p['where']}: {p['msg']}", file=sys.stderr)
    print(f"{len(errors)} error(s), {len(site['problems']) - len(errors)} warning(s)", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
