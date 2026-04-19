from __future__ import annotations

# Keys whose values are lists that should be concat+deduped on merge.
# Anything not listed here, if it's a list, is treated as a scalar (preserve existing).
LIST_MERGE_KEYS = {
    "sandbox.filesystem.allowWrite",
    "sandbox.filesystem.denyWrite",
    "sandbox.filesystem.allowRead",
    "sandbox.filesystem.denyRead",
    "sandbox.network.allowedDomains",
    "sandbox.network.allowUnixSockets",
    "sandbox.network.allowLocalBinding",
    "sandbox.excludedCommands",
    "sandbox.allowUnsandboxedCommands",
    "permissions.allow",
    "permissions.deny",
    "permissions.ask",
    "permissions.additionalDirectories",
}


def _dedupe(seq):
    seen = set()
    out = []
    for item in seq:
        key = json_key(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def json_key(v):
    import json
    return json.dumps(v, sort_keys=True)


def merge(existing: dict, preset: dict, *, force: bool, path: str = "") -> dict:
    """Merge preset into existing. Returns new dict; does not mutate inputs."""
    out = dict(existing)
    for k, pv in preset.items():
        sub = f"{path}.{k}" if path else k
        ev = out.get(k)
        if isinstance(pv, dict) and isinstance(ev, dict):
            out[k] = merge(ev, pv, force=force, path=sub)
        elif isinstance(pv, list) and sub in LIST_MERGE_KEYS:
            out[k] = _dedupe((ev or []) + pv)
        else:
            if k in out and not force:
                continue
            out[k] = pv
    return out
