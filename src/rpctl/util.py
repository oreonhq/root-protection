import os
import shutil
import subprocess
import sys
from typing import List, Optional, Sequence, Tuple


class RpError(Exception):
    pass


def which(name: str) -> Optional[str]:
    return shutil.which(name)


def require_root() -> None:
    if os.geteuid() != 0:
        raise RpError("must run as root")


def _fmt_argv(argv: Sequence[str]) -> str:
    parts = []
    for a in argv:
        if any(c in a for c in ' \t\n#"\'') or not a:
            parts.append(repr(a))
        else:
            parts.append(a)
    return " ".join(parts)


def run(
    argv: Sequence[str],
    *,
    check: bool = True,
    capture: bool = True,
    input_text: Optional[str] = None,
    env: Optional[dict] = None,
) -> subprocess.CompletedProcess:
    merged = None
    if env is not None:
        merged = os.environ.copy()
        merged.update(env)
    try:
        return subprocess.run(
            list(argv),
            check=check,
            text=True,
            input=input_text,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            env=merged,
        )
    except FileNotFoundError as e:
        raise RpError(f"missing command: {argv[0]}") from e
    except subprocess.CalledProcessError as e:
        chunks = []
        if e.stdout and e.stdout.strip():
            chunks.append(e.stdout.strip())
        if e.stderr and e.stderr.strip():
            chunks.append(e.stderr.strip())
        msg = f"command failed ({e.returncode}): {_fmt_argv(argv)}"
        if chunks:
            msg += "\n" + "\n".join(chunks)
        raise RpError(msg) from e


def run_out(argv: Sequence[str], **kwargs) -> str:
    return (run(argv, **kwargs).stdout or "").strip()


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def ok(msg: str) -> None:
    print(msg)


def parse_kv_lines(text: str, sep: str = "=") -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or sep not in line:
            continue
        k, v = line.split(sep, 1)
        out[k.strip()] = v.strip().strip('"')
    return out


def ensure_dir(path: str, mode: int = 0o755) -> None:
    os.makedirs(path, mode=mode, exist_ok=True)


def journal(msg: str, priority: str = "info") -> None:
    if which("logger"):
        try:
            run(["logger", "-t", "root-protection", "-p", f"user.{priority}", msg], check=False)
        except RpError:
            pass


def wall(msg: str) -> None:
    if which("wall"):
        try:
            run(["wall", f"root-protection: {msg}"], check=False, capture=False)
        except RpError:
            pass
