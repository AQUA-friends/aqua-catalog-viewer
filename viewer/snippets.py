"""Copy-paste snippets for a source, generated from the parsed catalog data.

Tabs per source:
  gsv driver   -> AQUA per engine (gsv is the default, so it omits `engine=`), YAML
  zarr/netcdf  -> AQUA, plain intake, YAML
  other        -> YAML

`metadata.machine` (a string or list, inherited from the parent nodes, see load.py) overrides the
automatic machine list: only the declared machines are shown, without the "may not be there" warning.
Machines without values in machine.yaml use the catalog defaults. gsv/z3fdb are local access (declared
machines only), polytope is online; for other drivers an "online" badge appears when the path or its
defaults are remote URLs.

Plain intake needs every {{ var }} of the source resolved. Source parameters have defaults;
catalog-level variables (LRA_PATH, ZARR_PATH, ... declared under `metadata.parameters` of
catalog.yaml) are machine dependent, so the intake tab carries one snippet per machine whose
machine.yaml sets all of them, plus "online" when every catalog default is a remote URL.
"""
import json
import re

import yaml

TEMPLATE = re.compile(r"\{\{\s*(\w+)\s*\}\}")
REMOTE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)  # s3://, https://, gs://, ...
BUILTIN = {"CATALOG_DIR"}
ONLINE = "online"
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


def catalog_vars_used(leaf):
    """Template variables of the source args that are not source parameters (e.g. LRA_PATH)."""
    used = set(TEMPLATE.findall(json.dumps(leaf["args"], default=str)))
    return used - set(leaf["parameters"]) - BUILTIN


def plain_intake_ok(leaf, variables=None):
    """Plain intake can open the source only if every {{ var }} in its args is a
    source parameter or a variable declared at catalog level."""
    return catalog_vars_used(leaf) <= set(variables or {})


def machine_choices(used, variables, machines):
    """[(name, {var: value})] for the machines that set every variable in `used`, in
    machine.yaml order, then ("online", defaults) when every catalog default is remote.
    A machine that does not list a variable is skipped: the catalog default is usually
    a path on another machine."""
    out = []
    for name, values in (machines or {}).items():
        if all(values.get(v) not in (None, "") for v in used):
            out.append((name, {v: values[v] for v in sorted(used)}))
    defaults = {v: (variables or {}).get(v) for v in sorted(used)}
    if all(isinstance(d, str) and REMOTE.match(d) for d in defaults.values()):
        out.append((ONLINE, defaults))
    return out


def canonical(name, machines):
    """The machine.yaml spelling of `name` (case-insensitive), else `name` itself."""
    for known in machines or {}:
        if known.lower() == name.lower():
            return known
    return name


def declared_machines(leaf, machines):
    """(names, online): the machines declared in metadata.machine (machine.yaml spelling), or
    None when the source declares nothing; `online` is True if "online" was listed."""
    raw = leaf.get("machines_declared")
    if not raw:
        return None, False
    names = list(dict.fromkeys(canonical(n, machines) for n in raw if n.lower() != ONLINE))
    return names, any(n.lower() == ONLINE for n in raw)


def is_online(leaf, variables):
    """The source reads a remote copy: its catalog variables all default to URLs or, without
    catalog variables, its path (source parameter defaults filled in) is a URL."""
    used = catalog_vars_used(leaf)
    if used:
        defaults = [(variables or {}).get(v) for v in used]
        return all(isinstance(d, str) and REMOTE.match(d) for d in defaults)
    defaults = {k: param_default(p) for k, p in leaf["parameters"].items()}
    args = leaf["args"]
    path = args.get("urlpath") or args.get("path")
    paths = path if isinstance(path, list) else [path]
    paths = [TEMPLATE.sub(lambda m: str(defaults.get(m.group(1), m.group(0))), x) for x in paths if isinstance(x, str)]
    return bool(paths) and all(REMOTE.match(x) for x in paths)


def declared_choices(used, variables, machines, names, online):
    """Like machine_choices, for declared machine names: the machine.yaml values when it sets every
    variable, else the catalog defaults (None when the default is missing too: no snippet)."""
    out = []
    for name in names:
        values = (machines or {}).get(name) or {}
        paths = {v: values.get(v) if values.get(v) not in (None, "") else (variables or {}).get(v) for v in sorted(used)}
        if all(x not in (None, "") for x in paths.values()):
            out.append((name, paths, all(values.get(v) not in (None, "") for v in used)))
    if online:
        defaults = {v: (variables or {}).get(v) for v in sorted(used)}
        out.append((ONLINE, defaults, False))
    return out


def machine_badges(leaf, variables, machines, online_ok=True):
    """[{name, kind}]: machines (declared, else the automatic ones) then online."""
    names, online_decl = declared_machines(leaf, machines)
    used = catalog_vars_used(leaf)
    if names is None:
        names = [n for n, _ in machine_choices(used, variables, machines) if n != ONLINE] if used else []
    badges = [{"name": n, "kind": "machine"} for n in names]
    if online_ok and (online_decl or is_online(leaf, variables)):
        badges.append({"name": ONLINE, "kind": "online"})
    return badges


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


MERGE_PATCH = [
    "# This catalog uses YAML merge keys (`<<: *anchor`), which intake 2.0.9 cannot read:",
    "# load YAML the standard way (duplicate keys are no longer reported).",
    "import yaml",
    "import intake.utils",
    "intake.utils.no_duplicates_constructor = yaml.SafeLoader.construct_yaml_map",
]


def intake_code(catalog, trail, repo_name, params, machine=None, paths=None, merge_keys=False, defaults=False):
    model, exp, source = trail
    lines = [
        "# Needs intake>=2.0.9, intake-xarray and jinja2",
        "import intake",
        "",
        *(MERGE_PATCH + [""] if merge_keys else []),
        f'cat = intake.open_catalog("/path/to/{repo_name}/catalogs/{catalog}/catalog.yaml")',
    ]
    kwargs = list(params) + sorted((paths or {}).items())
    if not kwargs:
        lines.append(f'ds = cat["{model}"]["{exp}"]["{source}"].to_dask()')
        return "\n".join(lines)
    lines += [
        "# `_entries[...]` is required to pass parameters: the public form",
        "# cat[model][exp][source](...) silently ignores them in intake 2.",
    ]
    if paths:
        if machine == ONLINE:
            where = "the remote copy (no machine needed)"
        elif defaults:
            where = f"{machine} (not set in machine.yaml: catalog defaults)"
        else:
            where = f"{machine} (from machine.yaml)"
        lines += ["# Catalog paths must be passed to the entry too; these are for " + where + "."]
    lines.append(f'entry = cat["{model}"]["{exp}"]._entries["{source}"]')
    if paths:
        lines += ["ds = entry("] + [f"    {k}={v!r}," for k, v in kwargs] + [").to_dask()"]
    else:
        lines.append(f"ds = entry({', '.join(f'{k}={v!r}' for k, v in kwargs)}).to_dask()")
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


def intake_tab(repo_name, catalog, leaf, variables, machines):
    """The intake tab, or None. With catalog-level variables it has `choices`:
    [{name, code}] (one per machine, see machine_choices) and `code` is the first one."""
    if leaf["driver"] not in ("zarr", "netcdf") or not plain_intake_ok(leaf, variables):
        return None
    trail = leaf["trail"]
    params = [(k, param_default(p)) for k, p in leaf["parameters"].items() if param_default(p) is not None]
    tab = {"id": "intake", "label": "intake", "lang": "python"}
    used = catalog_vars_used(leaf)
    merge = bool(leaf.get("merge_keys"))  # intake 2.0.9 needs a patch for `<<: *anchor`
    if not used:
        return {**tab, "badges": machine_badges(leaf, variables, machines),
                "code": intake_code(catalog, trail, repo_name, params, merge_keys=merge)}
    names, _ = declared_machines(leaf, machines)
    if names is None:
        choices = [{"name": name, "code": intake_code(catalog, trail, repo_name, params, name, paths, merge)}
                   for name, paths in machine_choices(used, variables, machines)]
        note = ("Paths come from the catalog's machine.yaml (online: the remote default of catalog.yaml). "
                "A listed machine is not a promise that the whole dataset is there: only part of it "
                "may be synced on that machine.")
    else:
        online = is_online(leaf, variables)  # a declared "online" with local defaults has no snippet
        choices = [{"name": name, "code": intake_code(catalog, trail, repo_name, params, name, paths, merge,
                                                      defaults=not own)}
                   for name, paths, own in declared_choices(used, variables, machines, names, online)]
        note = ("Machines are those declared in the source metadata. Paths come from the catalog's machine.yaml, "
                "or from the catalog.yaml defaults when the machine is not described there.")
    if not choices:
        return None
    return {**tab, "code": choices[0]["code"], "choices": choices, "note": note}


def availability(leaf, engines, variables=None, machines=None):
    """Badges for the Details row: where the source can be read."""
    if leaf["driver"] == "gsv":
        names, _ = declared_machines(leaf, machines)
        badges = [{"name": n, "kind": "machine"} for n in names or []]
        if "polytope" in engines:
            badges.append({"name": ONLINE, "kind": "online"})
        return badges
    return machine_badges(leaf, variables, machines)


def leaf_tabs(repo_name, catalog, leaf, engines, variables=None, machines=None):
    """List of {id, label, lang, code, note, choices} for the snippet box of one source.
    `variables` (name -> default) and `machines` (machine -> {name: value}) are the
    catalog-level variables of catalog.yaml and machine.yaml."""
    trail = leaf["trail"]
    tabs = []
    if len(trail) == 3 and leaf["kind"] == "source":
        realization = leaf["parameters"].get("realization")
        extra = [("realization", param_default(realization))] if param_default(realization) is not None else []
        if leaf["driver"] == "gsv":
            for engine in engines:
                kw = extra if engine == "gsv" else extra + [("engine", engine)]
                label = "AQUA · gsv (default)" if engine == "gsv" else f"AQUA · {engine}"
                if engine == "polytope":
                    badges = [{"name": ONLINE, "kind": "online"}]
                else:  # gsv, z3fdb: local access, only where the metadata says
                    badges = [{"name": n, "kind": "machine"} for n in declared_machines(leaf, machines)[0] or []]
                tabs.append({"id": f"aqua-{engine}", "label": label, "lang": "python", "badges": badges,
                             "code": aqua_code(catalog, trail, repo_name, kw)})
        else:
            tabs.append({"id": "aqua", "label": "AQUA", "lang": "python",
                         "badges": machine_badges(leaf, variables, machines),
                         "code": aqua_code(catalog, trail, repo_name, extra)})
            intake = intake_tab(repo_name, catalog, leaf, variables, machines)
            if intake:
                tabs.append(intake)
    tabs.append({"id": "yaml", "label": "YAML", "lang": "yaml", "code": leaf_yaml(leaf),
                 "note": "Resolved view: YAML anchors and merge keys are expanded."})
    return tabs


def install_blocks(repo_name, url, catalog, is_open):
    """[(label, code)] to install one catalog: online (open repos only) and editable."""
    blocks = []
    if is_open:
        blocks.append(("Online", f"aqua add {catalog}"))
    blocks.append(("Editable", f"git clone {url}\naqua add {catalog} -e path/to/{repo_name}/catalogs/{catalog}"))
    return blocks
