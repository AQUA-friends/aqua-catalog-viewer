"""Short name and long name of ECMWF parameters, for the link tooltips on source pages.

One request to the parameter database API at build time returns every parameter. If it
cannot be reached the build carries on and the tooltips fall back to a generic text.
"""
import json
import sys
import urllib.request

PARAM_API_URL = "https://codes.ecmwf.int/parameter-database/api/v1/param/?format=json"


def parse_names(rows, wanted):
    """{id: {"short": ..., "name": ...}} for the wanted ids found in the API's list of params."""
    return {r["id"]: {"short": r.get("shortname") or "", "name": r.get("name") or ""}
            for r in rows if r.get("id") in wanted}


def fetch_names(wanted, url=PARAM_API_URL, timeout=60):
    if not wanted:
        return {}
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            names = parse_names(json.load(resp), wanted)
    except (OSError, ValueError) as e:  # URLError and timeouts are OSErrors; bad JSON is a ValueError
        print(f"WARNING parameter names not fetched ({e}); tooltips will be generic", file=sys.stderr)
        return {}
    missing = sorted(wanted - names.keys())
    if missing:
        print(f"WARNING {len(missing)} param id(s) unknown to ECMWF: {', '.join(map(str, missing[:10]))}",
              file=sys.stderr)
    return names
