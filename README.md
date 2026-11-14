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
claudelator apply             # add the bundled preset to ~/.claude/settings.json
claudelator apply --local     # ./.claude/settings.local.json
claudelator apply --project   # ./.claude/settings.json
claudelator apply --dry-run   # print the resulting settings without writing
```

There is a single preset (`src/claudelator/preset.json`) that enables the sandbox and opens write access and network domains for common toolchains (cargo, uv/pip, npm/yarn/pnpm, dotnet, go, gh, aws, playwright, keyring) and excludes `zaira` from the sandbox. Applying it adds missing list entries (deduped) and keeps any scalar you already set. Writes are atomic with a dated `.bak` backup the first time each day. Default scope is global.

## Herdr Desktop on WSL

Connect the Windows [Herdr Desktop](https://vivainio.github.io/articles/terminal/herdr-desktop-wsl/) app to `herdr-core` in WSL over SSH to localhost. Run it in your own WSL shell (not inside the Claude Code sandbox, and not with `sudo`):

```bash
claudelator herdr --dry-run   # preview
claudelator herdr             # install hc + sshd, create key, authorize it, add `Host wsl`, disable SSH password login
claudelator herdr check       # sshd, connections, herdr-core processes, hc ls
```

It creates `%USERPROFILE%\.ssh\herdr_desktop_ed25519` **without a passphrase**, so keep `/mnt/c/Users/*/.ssh` out of the sandbox's `allowRead`. Password login is only disabled after a key login to localhost succeeds; if that test fails the command stops and leaves it enabled. Afterwards add the machine in the app under Settings -> Machines. Use `--host` and `--port` to change the alias and port.
