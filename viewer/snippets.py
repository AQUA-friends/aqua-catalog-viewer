"""Copy-paste snippets for a source, generated from the parsed catalog data.

Tabs per source:
  gsv driver   -> AQUA per engine (gsv is the default, so it omits `engine=`), YAML
  zarr/netcdf  -> AQUA, plain intake (only when nothing needs AQUA's machine config), YAML
  other        -> YAML
"""
import json
import re

import yaml

TEMPLATE = re.compile(r"\{\{\s*(\w+)\s*\}\}")
DATE = re.compile(r"^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2}))?$")


def fmt_date(value, time=False):
    """19900101T0000 -> 1990-01-01 (or 1990-01-01 00:00); anything else is returned as is."""
    m = DATE.match(str(value))
    if not m:
        return str(value)
    y, mo, d, h, mi = m.groups()
    out = f"{y}-{mo}-{d}"
    return f"{out} {h}:{mi}" if time and h else out


def param_default(p):
    if not isinstance(p, dict):
        return None
    if p.get("default") is not None:
        return p["default"]
    allowed = p.get("allowed")
    return allowed[0] if allowed else None


def plain_intake_ok(leaf):
    """Plain intake can open the source only if every {{ var }} in its args is a
    source parameter; machine variables like LRA_PATH are resolved by AQUA only."""
    used = set(TEMPLATE.findall(json.dumps(leaf["args"], default=str)))
    return used <= set(leaf["parameters"])


def aqua_code(catalog, trail, repo_name, extra):
    model, exp, source = trail
    lines = [
        "# One-time setup, if the catalog is not installed yet:",
        f"#   aqua add {catalog} -e /path/to/{repo_name}/catalogs/{catalog}",
        "",
        "from aqua import Reader",
        "",
        "reader = Reader(",
        f'    catalog="{catalog}",',
        f'    model="{model}",',
        f'    exp="{exp}",',
        f'    source="{source}",',
    ]
    lines += [f"    {k}={v!r}," for k, v in extra]
    lines += [")", "data = reader.retrieve()"]
    return "\n".join(lines)


def intake_code(catalog, trail, repo_name, params):
    model, exp, source = trail
    lines = [
        "# Needs intake>=2.0.9 and intake-xarray",
        "import intake",
        "",
        f'cat = intake.open_catalog("/path/to/{repo_name}/catalogs/{catalog}/catalog.yaml")',
    ]
    if params:
        kwargs = ", ".join(f"{k}={v!r}" for k, v in params)
        lines += [
            "# `_entries[...]` is required to pass parameters: the public form",
            "# cat[model][exp][source](...) silently ignores them in intake 2.",
            f'entry = cat["{model}"]["{exp}"]._entries["{source}"]',
            f"ds = entry({kwargs}).to_dask()",
        ]
    else:
        lines.append(f'ds = cat["{model}"]["{exp}"]["{source}"].to_dask()')
    return "\n".join(lines)


class _NoAlias(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _list(dumper, data):
    """Lists of plain scalars (levels, variable IDs) on one wrapped line instead of one per line."""
    flat = all(isinstance(x, (str, int, float, bool, type(None))) for x in data)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flat or None)


_NoAlias.add_representer(list, _list)


def leaf_yaml(leaf):
    spec = {
        k: leaf[k]
        for k in ("description", "driver", "metadata", "args", "parameters")
        if k == "driver" or leaf.get(k)
    }
    return yaml.dump({leaf["name"]: spec}, Dumper=_NoAlias, sort_keys=False, width=100, allow_unicode=True)


def leaf_tabs(repo_name, catalog, leaf, engines):
    """List of {id, label, lang, code, note} for the snippet box of one source."""
    trail = leaf["trail"]
    tabs = []
    if len(trail) == 3 and leaf["kind"] == "source":
        realization = leaf["parameters"].get("realization")
        extra = [("realization", param_default(realization))] if param_default(realization) is not None else []
        if leaf["driver"] == "gsv":
            for engine in engines:
                kw = extra if engine == "gsv" else extra + [("engine", engine)]
                label = "AQUA · gsv (default)" if engine == "gsv" else f"AQUA · {engine}"
                tabs.append({"id": f"aqua-{engine}", "label": label, "lang": "python",
                             "code": aqua_code(catalog, trail, repo_name, kw)})
        else:
            tabs.append({"id": "aqua", "label": "AQUA", "lang": "python",
                         "code": aqua_code(catalog, trail, repo_name, extra)})
            if leaf["driver"] in ("zarr", "netcdf") and plain_intake_ok(leaf):
                params = [(k, param_default(p)) for k, p in leaf["parameters"].items() if param_default(p) is not None]
                tabs.append({"id": "intake", "label": "intake", "lang": "python",
                             "code": intake_code(catalog, trail, repo_name, params)})
    tabs.append({"id": "yaml", "label": "YAML", "lang": "yaml", "code": leaf_yaml(leaf),
                 "note": "Resolved view: YAML anchors and merge keys are expanded."})
    return tabs
