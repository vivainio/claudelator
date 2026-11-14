"""Set up Herdr Desktop (Windows) -> herdr-core (WSL) over SSH to localhost.

Run from your own WSL shell, not from inside the Claude Code sandbox: it needs
sudo, writes ~/.ssh, writes the Windows profile and calls ssh-keygen.exe
through WSL interop.
"""
from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

KEY_NAME = "herdr_desktop_ed25519"
INSTALL_CMD = "curl -fsSL https://releases.herdr.dev/core/install.sh | sh"


def _say(msg: str) -> None:
    print(msg, flush=True)


def _step(n: int, title: str) -> None:
    _say(f"\n[{n}] {title}")


def _run(cmd: list[str] | str, *, dry: bool, shell: bool = False, check: bool = True, **kw):
    shown = cmd if isinstance(cmd, str) else " ".join(cmd)
    if dry:
        _say(f"    would run: {shown}")
        return None
    _say(f"    $ {shown}")
    return subprocess.run(cmd, shell=shell, check=check, **kw)


def _out(cmd: list[str], **kw) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


_WIN_DIRS = ["/mnt/c/Windows/System32", "/mnt/c/Windows/System32/OpenSSH"]


def _winexe(name: str) -> str | None:
    """Find a Windows executable even when WSL doesn't append the Windows PATH."""
    found = shutil.which(name)
    if found:
        return found
    for d in _WIN_DIRS:
        if (Path(d) / name).exists():
            return str(Path(d) / name)
    return None


def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def _windows_profile() -> Path | None:
    raw = _out([_winexe("cmd.exe") or "cmd.exe", "/c", "echo %USERPROFILE%"], cwd="/mnt/c")
    if not raw:
        return None
    unix = _out(["wslpath", "-u", raw.replace("\r", "")])
    return Path(unix) if unix else None


def _port_listening(port: int) -> bool:
    out = _out(["ss", "-ltn"]) or ""
    return any(f":{port} " in line or line.rstrip().endswith(f":{port}") for line in out.splitlines())


def _backup(path: Path) -> None:
    bak = path.with_name(f"{path.name}.{date.today().isoformat()}.bak")
    if path.exists() and not bak.exists():
        shutil.copy2(path, bak)


def setup(args) -> int:
    dry = args.dry_run
    if not _is_wsl():
        _say("error: this command is for WSL2 (no Microsoft kernel detected)")
        return 1
    profile = _windows_profile()
    if profile is None:
        _say("error: could not determine the Windows profile (is WSL interop enabled / cmd.exe on PATH?)")
        return 1
    if _winexe("ssh.exe") is None or _winexe("ssh-keygen.exe") is None:
        _say("error: Windows OpenSSH client (ssh.exe, ssh-keygen.exe) not found on PATH")
        return 1

    if os.geteuid() == 0:
        _say("error: run as your normal user, not root/sudo (it uses ~/.ssh and sudo itself when needed)")
        return 1
    wsl_user = getpass.getuser()
    win_ssh = profile / ".ssh"
    key = win_ssh / KEY_NAME
    pub = win_ssh / f"{KEY_NAME}.pub"
    _say(f"WSL user: {wsl_user}\nWindows profile: {profile}\nHost alias: {args.host}")
    if dry:
        _say("(dry run: nothing will be changed)")

    # 0. herdr-core
    _step(0, "herdr-core (hc)")
    hc = shutil.which("hc") or (str(p) if (p := Path.home() / ".local/bin/hc").exists() else None)
    if hc:
        _say(f"    ok: {hc}")
    else:
        _run(INSTALL_CMD, dry=dry, shell=True)

    # 1. sshd
    _step(1, "OpenSSH server")
    if subprocess.run(["dpkg", "-s", "openssh-server"], capture_output=True).returncode == 0:
        _say("    ok: openssh-server installed")
    else:
        _run(["sudo", "apt", "update"], dry=dry)
        _run(["sudo", "apt", "install", "-y", "openssh-server"], dry=dry)
    if _port_listening(args.port):
        _say(f"    ok: listening on :{args.port}")
    else:
        _run(["sudo", "service", "ssh", "start"], dry=dry)
        _say("    note: this lasts until WSL shuts down; enable systemd + `systemctl enable ssh` for auto-start")

    # 2. key (Windows side)
    _step(2, "dedicated ed25519 key on Windows (no passphrase)")
    if key.exists():
        _say(f"    ok: {key}")
    else:
        if not dry:
            win_ssh.mkdir(parents=True, exist_ok=True)
        winkey = _out(["wslpath", "-w", str(key)]) or str(key)
        _run([_winexe("ssh-keygen.exe"), "-t", "ed25519", "-N", "", "-f", winkey, "-C", "herdr-desktop"], dry=dry)

    # 3. authorize
    _step(3, "authorize the public key in WSL")
    auth = Path.home() / ".ssh" / "authorized_keys"
    if dry and not pub.exists():
        _say(f"    would append {pub} to {auth}")
    elif not pub.exists():
        _say(f"error: {pub} missing")
        return 1
    else:
        line = pub.read_text().strip()
        existing = auth.read_text().splitlines() if auth.exists() else []
        if line in existing:
            _say("    ok: already authorized")
        elif dry:
            _say(f"    would append {pub.name} to {auth}")
        else:
            auth.parent.mkdir(mode=0o700, exist_ok=True)
            with auth.open("a") as f:
                if existing and not auth.read_text().endswith("\n"):
                    f.write("\n")
                f.write(line + "\n")
            auth.chmod(0o600)
            _say(f"    added to {auth}")

    # 4. SSH config entry on Windows
    _step(4, "Windows ssh config host entry")
    cfg = win_ssh / "config"
    block = (
        f"Host {args.host}\n"
        f"    HostName localhost\n"
        f"    Port {args.port}\n"
        f"    User {wsl_user}\n"
        f"    IdentityFile ~/.ssh/{KEY_NAME}\n"
    )
    text = cfg.read_text() if cfg.exists() else ""
    if any(ln.split()[:2] == ["Host", args.host] for ln in text.splitlines()):
        _say(f"    ok: Host {args.host} already in {cfg}")
    elif dry:
        _say(f"    would append to {cfg}:\n" + "".join(f"      {l}\n" for l in block.splitlines()))
    else:
        win_ssh.mkdir(parents=True, exist_ok=True)
        _backup(cfg)
        sep = "" if not text or text.endswith("\n") else "\n"
        cfg.write_text(text + sep + ("\n" if text else "") + block)
        _say(f"    added to {cfg}")

    # 5. lock down (always; only after key login is proven to work)
    _step(5, "disable SSH password login")
    if dry:
        _say("    would test key login, then set PasswordAuthentication no and restart ssh")
    else:
        _say("    testing key login from Windows...")
        t = subprocess.run([
            _winexe("ssh.exe"), "-i", _out(["wslpath", "-w", str(key)]) or str(key),
            "-o", "PasswordAuthentication=no", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
            "-p", str(args.port), f"{wsl_user}@localhost", "true",
        ])
        if t.returncode != 0:
            _say("    key login failed - NOT disabling password login (fix key login and re-run)")
            return 1
        _run(["sudo", "sed", "-i", r"s/^#\?PasswordAuthentication.*/PasswordAuthentication no/",
              "/etc/ssh/sshd_config"], dry=False)
        _run(["sudo", "service", "ssh", "restart"], dry=False)

    _say(f"\nNext: in Herdr Desktop open Settings -> Machines -> Add machine and pick '{args.host}'."
         "\nThen verify with: claudelator herdr check")
    return 0


def check(args) -> int:
    rc = 0
    _step(1, "sshd")
    ok = _port_listening(args.port)
    _say(f"    {'ok' if ok else 'FAIL'}: listening on :{args.port}")
    rc |= not ok
    _step(2, "established SSH connections")
    _say("    " + ((_out(["ss", "-tn", "state", "established", f"( sport = :{args.port} )"]) or "none").replace("\n", "\n    ")))
    _step(3, "herdr-core processes")
    ps = _out(["ps", "-eo", "pid,lstart,args"]) or ""
    lines = [l for l in ps.splitlines() if "herdr-core" in l]
    _say("    " + ("\n    ".join(lines) if lines else "none (add the machine in the app first)"))
    _step(4, "hc ls")
    hc = shutil.which("hc")
    if hc:
        subprocess.run([hc, "ls"])
    else:
        _say("    FAIL: hc not on PATH")
        rc = 1
    profile = _windows_profile()
    if profile and (profile / ".ssh" / KEY_NAME).exists():
        _step(5, "key exposure")
        _say("    warning: the key has no passphrase. Keep /mnt/c/Users/*/.ssh out of the"
             " Claude sandbox's allowRead - a readable key plus sshd on localhost is an unsandboxed shell")
    return rc


def cmd_herdr(args) -> None:
    sys.exit(check(args) if args.action == "check" else setup(args))
