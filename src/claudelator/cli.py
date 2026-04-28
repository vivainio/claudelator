from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date
from importlib.resources import files
from pathlib import Path

from .merge import merge

USER_PRESET_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "claudelator" / "presets"


def preset_paths() -> dict[str, Path]:
    """Discover presets. User dir overrides packaged."""
    found: dict[str, Path] = {}
    pkg_dir = files("claudelator").joinpath("presets")
    for p in pkg_dir.iterdir():  # type: ignore[attr-defined]
        if p.name.endswith(".json"):
            found[p.name[:-5]] = Path(str(p))
    if USER_PRESET_DIR.is_dir():
        for p in USER_PRESET_DIR.glob("*.json"):
            found[p.stem] = p
    return found


def _expand_env(obj):
    if isinstance(obj, str):
        return os.path.expandvars(obj)
    if isinstance(obj, list):
        return [_expand_env(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    return obj


def load_preset(name: str) -> dict:
    presets = preset_paths()
    if name not in presets:
        sys.exit(f"unknown preset: {name} (available: {', '.join(sorted(presets)) or 'none'})")
    env = {**os.environ, "UID": str(os.getuid())}
    raw = presets[name].read_text()
    # Use a temporary environ override for $UID expansion
    old_uid = os.environ.get("UID")
    os.environ["UID"] = env["UID"]
    try:
        return _expand_env(json.loads(raw))
    finally:
        if old_uid is None:
            os.environ.pop("UID", None)
        else:
            os.environ["UID"] = old_uid


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


def cmd_list(args):
    presets = preset_paths()
    if not presets:
        print("no presets found")
        return
    for name in sorted(presets):
        print(f"{name}\t{presets[name]}")


def cmd_show(args):
    print(json.dumps(load_preset(args.name), indent=2))


def cmd_diff(args):
    path = settings_path(args)
    existing = load_settings(path)
    merged = existing
    for name in args.names:
        merged = merge(merged, load_preset(name), force=args.force)
    before = json.dumps(existing, indent=2, sort_keys=True).splitlines()
    after = json.dumps(merged, indent=2, sort_keys=True).splitlines()
    import difflib
    out = list(difflib.unified_diff(before, after, fromfile=str(path), tofile="(after merge)", lineterm=""))
    if not out:
        print("no changes")
    else:
        print("\n".join(out))


def cmd_sandbox(args):
    path = settings_path(args)
    existing = load_settings(path)
    key = "allowRead" if args.read else "allowWrite"
    addition = {"sandbox": {"filesystem": {key: [str(Path(p).expanduser().resolve()) for p in args.paths]}}}
    merged = merge(existing, addition, force=False)
    if merged == existing:
        print(f"{path}: already whitelisted")
        return
    if args.dry_run:
        print(json.dumps(merged, indent=2))
        return
    write_atomic(path, merged)
    print(f"{path}: added {len(args.paths)} path(s) to sandbox.filesystem.{key}")


def cmd_apply(args):
    path = settings_path(args)
    existing = load_settings(path)
    merged = existing
    for name in args.names:
        merged = merge(merged, load_preset(name), force=args.force)
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

    def add_scope(sp):
        g = sp.add_mutually_exclusive_group()
        g.add_argument("--local", action="store_true", help="./.claude/settings.local.json")
        g.add_argument("--project", action="store_true", help="./.claude/settings.json")
        sp.add_argument("--force", action="store_true", help="overwrite existing scalar values")

    sp = sub.add_parser("list"); sp.set_defaults(func=cmd_list)
    sp = sub.add_parser("show"); sp.add_argument("name"); sp.set_defaults(func=cmd_show)
    sp = sub.add_parser("apply"); sp.add_argument("names", nargs="+"); add_scope(sp)
    sp.add_argument("--dry-run", action="store_true"); sp.set_defaults(func=cmd_apply)
    sp = sub.add_parser("diff"); sp.add_argument("names", nargs="+"); add_scope(sp); sp.set_defaults(func=cmd_diff)
    sp = sub.add_parser("sandbox", help="add path(s) to sandbox filesystem whitelist")
    sp.add_argument("paths", nargs="+")
    sp.add_argument("--read", action="store_true", help="add to allowRead instead of allowWrite")
    sp.add_argument("--dry-run", action="store_true")
    add_scope(sp)
    sp.set_defaults(func=cmd_sandbox)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
