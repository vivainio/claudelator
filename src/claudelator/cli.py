from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date
from importlib.resources import files
from pathlib import Path

from .herdr import cmd_herdr

def load_preset() -> dict:
    raw = files("claudelator").joinpath("preset.json").read_text()
    old = os.environ.get("UID")
    os.environ["UID"] = str(os.getuid())
    try:
        return _expand_env(json.loads(raw))
    finally:
        if old is None:
            os.environ.pop("UID", None)
        else:
            os.environ["UID"] = old


def _expand_env(obj):
    if isinstance(obj, str):
        return os.path.expandvars(obj)
    if isinstance(obj, list):
        return [_expand_env(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    return obj


def add_missing(existing: dict, preset: dict) -> dict:
    """Add preset entries to existing: lists are unioned, existing scalars are kept."""
    out = dict(existing)
    for k, v in preset.items():
        cur = out.get(k)
        if isinstance(v, dict) and isinstance(cur, dict):
            out[k] = add_missing(cur, v)
        elif isinstance(v, list) and isinstance(cur, list):
            out[k] = cur + [x for x in v if x not in cur]
        elif k not in out:
            out[k] = v
    return out


def settings_path(args) -> Path:
    if args.local:
        return Path.cwd() / ".claude" / "settings.local.json"
    if args.project:
        return Path.cwd() / ".claude" / "settings.json"
    return Path.home() / ".claude" / "settings.json"


def load_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text().strip()
    return json.loads(text) if text else {}


def write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + f".bak.{date.today().isoformat()}")
        if not backup.exists():
            shutil.copy2(path, backup)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)


def cmd_apply(args):
    path = settings_path(args)
    existing = load_settings(path)
    merged = add_missing(existing, load_preset())
    if merged == existing:
        print(f"{path}: no changes")
        return
    if args.dry_run:
        print(json.dumps(merged, indent=2))
        return
    write_atomic(path, merged)
    print(f"{path}: updated")


def main(argv=None):
    p = argparse.ArgumentParser(prog="claudelator")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("apply", help="add the bundled sandbox preset to Claude Code settings")
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--local", action="store_true", help="./.claude/settings.local.json")
    g.add_argument("--project", action="store_true", help="./.claude/settings.json")
    sp.add_argument("--dry-run", action="store_true", help="print the resulting settings without writing")
    sp.set_defaults(func=cmd_apply)

    sp = sub.add_parser("herdr", help="set up Herdr Desktop (Windows) -> herdr-core in WSL over SSH")
    sp.add_argument("action", nargs="?", choices=["setup", "check"], default="setup")
    sp.add_argument("--host", default="wsl", help="ssh host alias to create (default: wsl)")
    sp.add_argument("--port", type=int, default=22)
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(func=cmd_herdr)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
