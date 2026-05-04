# claudelator

Apply preset bundles to [Claude Code](https://docs.claude.com/claude-code) `settings.json` — sandbox filesystem whitelists, allowed network domains, permissions, and so on.

Writing the same `sandbox.filesystem.allowWrite` entries into every project's `.claude/settings.json` gets old fast. `claudelator` lets you keep those entries in reusable preset files and merge them into your global or per-project settings idempotently.

## Install

```bash
uv tool install claudelator
```

Or from source:

```bash
git clone https://github.com/vivainio/claudelator
cd claudelator
uv tool install -e .
```

## Usage

```bash
claudelator list                      # show available presets
claudelator show uv                   # print a preset's JSON
claudelator diff base uv              # preview what apply would change
claudelator apply base uv             # merge into ~/.claude/settings.json
claudelator apply base uv --local     # ./.claude/settings.local.json
claudelator apply base uv --project   # ./.claude/settings.json
claudelator apply base uv --dry-run   # print result without writing

claudelator sandbox .                 # add cwd to sandbox allowWrite
claudelator sandbox ~/work /tmp/foo   # multiple paths
claudelator sandbox . --read          # add to allowRead instead
claudelator sandbox . --local         # apply to project-local settings
```

Default scope is **global** (`~/.claude/settings.json`). Use `--local` or `--project` for per-project files.

## Merge semantics

- Dicts are deep-merged.
- Known array keys (`sandbox.filesystem.allowWrite`, `sandbox.network.allowedDomains`, `permissions.allow`, etc.) are concatenated and deduped.
- Scalars are preserved if they already exist. Pass `--force` to overwrite.
- Writes are atomic and create a dated `.bak` backup the first time each day.

## Bundled presets

- `base` — enables the sandbox
- `uv` — write access to the uv cache; allows `pypi.org`, `files.pythonhosted.org`
- `node` — write access to npm/yarn/pnpm caches; allows their registries
- `aws` — write access to AWS SSO/CLI cache; allows AWS API domains
- `zaira` — runs `zaira` outside the sandbox so its `wincred.exe` subprocess can reach Windows Credential Manager via the WSL interop socket (which the sandbox blocks). Requires a Claude Code restart after applying.

## Custom presets

Drop JSON files into `~/.config/claudelator/presets/`. They override packaged presets with the same name.

```json
{
  "sandbox": {
    "filesystem": {
      "allowWrite": ["~/.cache/my-tool"]
    },
    "network": {
      "allowedDomains": ["example.com"]
    }
  }
}
```

## License

MIT
