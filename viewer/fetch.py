"""Clone the repos listed in site.yaml into <repos-dir>/<name> (used by CI).

    python -m viewer.fetch --repos-dir repos

Each repo needs a `url` (and optionally `ref`, default main). A private repo declares
`auth: {user_env: ..., token_env: ...}`: those environment variables hold the credentials,
which are sent as an HTTP header via git's environment config, so they never appear in the
URL, the command line or .git/config.
"""
import argparse
import base64
import os
import subprocess
import sys
from pathlib import Path

import yaml


def clone_cmd(repo, dest, environ):
    """Return (command, extra_env) to shallow-clone one repo."""
    if not repo.get("url"):
        raise SystemExit(f"{repo['name']}: no `url` in site.yaml, cannot fetch")
    extra = {"GIT_TERMINAL_PROMPT": "0"}
    auth = repo.get("auth")
    if auth:
        user, token = environ.get(auth["user_env"]), environ.get(auth["token_env"])
        if not user or not token:
            raise SystemExit(f"{repo['name']} is private: set {auth['user_env']} and {auth['token_env']}")
        basic = base64.b64encode(f"{user}:{token}".encode()).decode()
        extra.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.extraHeader",
                     GIT_CONFIG_VALUE_0=f"Authorization: Basic {basic}")
    cmd = ["git", "clone", "--quiet", "--depth", "1", "--branch", repo.get("ref", "main"), repo["url"], str(dest)]
    return cmd, extra


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="site.yaml")
    ap.add_argument("--repos-dir", required=True)
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(args.config).read_text())
    jobs = []  # validate every repo (url, credentials, free destination) before cloning any
    for repo in cfg["repos"]:
        dest = Path(args.repos_dir) / repo["name"]
        if dest.exists():
            raise SystemExit(f"{dest} already exists; remove it or pick another --repos-dir")
        jobs.append((repo, *clone_cmd(repo, dest, os.environ)))
    for repo, cmd, extra in jobs:
        print(f"cloning {repo['name']} ({repo.get('ref', 'main')})")
        if subprocess.run(cmd, env={**os.environ, **extra}).returncode:
            raise SystemExit(f"git clone failed for {repo['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
