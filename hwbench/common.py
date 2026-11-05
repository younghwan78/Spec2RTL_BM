import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SUITE = ROOT / "benchmarks/core/suite.json"


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def portable_logs(obj, root):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "log" and isinstance(value, str) and Path(value).is_absolute():
                try:
                    obj[key] = str(Path(value).relative_to(Path(root).resolve()))
                except ValueError:
                    pass
            else:
                portable_logs(value, root)
    elif isinstance(obj, list):
        for value in obj:
            portable_logs(value, root)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"Invalid relative path: {value!r}")
    p = Path(value)
    if p.is_absolute() or any(x in ("..", ".", "") for x in value.split("/")):
        raise ValueError(f"Unsafe path: {value!r}")
    return p


def within(root, value):
    root = Path(root).resolve()
    p = root / relative_path(value)
    current = root
    for part in relative_path(value).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Symlink is not allowed: {current}")
    if not p.resolve().is_relative_to(root):
        raise ValueError(f"Path escapes root: {value}")
    return p


def load_suite(path=DEFAULT_SUITE):
    path = Path(path).resolve()
    s = json.loads(path.read_text())
    if s.get("schema_version") != 1 or not isinstance(s.get("tasks"), list) or not s["tasks"]:
        raise ValueError("Expected schema_version=1 and a nonempty task list")
    ids = set()
    hashes = {"suite.json": digest(canonical(s))}
    for task in s["tasks"]:
        tid = task["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", tid) or tid in ids:
            raise ValueError(f"Invalid or duplicate task ID: {tid}")
        ids.add(tid)
        base = within(path.parent, task["path"])
        if not task["files"] or len(set(task["files"])) != len(task["files"]):
            raise ValueError(f"Empty/duplicate files: {tid}")
        names = ["prompt.md"]
        for f in task["files"]:
            relative_path(f)
            if Path(f).suffix not in (".sv", ".v"):
                raise ValueError(f"Only RTL files may be submitted: {f}")
            names += [f"starter/{f}"]
        cids = set()
        if not task["checks"]:
            raise ValueError(f"No checks: {tid}")
        for c in task["checks"]:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", c["id"]) or c["id"] in cids:
                raise ValueError(f"Invalid/duplicate check: {tid}")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", c.get("top", "tb")):
                raise ValueError("Invalid top module")
            cids.add(c["id"])
            names.append(c["tb"])
        for name in names:
            f = within(base, name)
            hashes[f"{tid}/{name}"] = digest(f.read_bytes())
    s["_path"] = str(path)
    s["fingerprint"] = digest(canonical(hashes))
    s["file_hashes"] = hashes
    return s


def task_base(suite, task):
    return within(Path(suite["_path"]).parent, task["path"])


def tool_version(name):
    path = shutil.which(name)
    if not path:
        return {"available": False, "path": None, "version": None}
    flag = "-V" if name in ("iverilog", "vvp") else "--version"
    try:
        p = subprocess.run([path, flag], capture_output=True, text=True, timeout=10)
        lines = (p.stdout + p.stderr).splitlines()
        return {"available": p.returncode == 0, "path": path,
                "version": lines[0] if lines else "unknown"}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "path": path, "version": str(exc)}


def execute(argv, cwd, log, timeout=30, env=None, max_bytes=2_000_000):
    """No shell. Kill the entire process group on timeout/output exhaustion."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    result = {"argv": [str(x) for x in argv], "cwd": str(cwd), "log": str(log.resolve()),
              "returncode": None, "timeout": False, "output_limit": False}
    try:
        with log.open("wb") as stream:
            p = subprocess.Popen(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                 env=env, start_new_session=True, stdin=subprocess.DEVNULL)
            while p.poll() is None:
                if time.monotonic() - start > timeout or log.stat().st_size > max_bytes:
                    result["timeout"] = time.monotonic() - start > timeout
                    result["output_limit"] = log.stat().st_size > max_bytes
                    os.killpg(p.pid, signal.SIGKILL)
                    break
                time.sleep(0.02)
            result["returncode"] = p.wait()
            # A completed parent must not leave descendants alive.
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if log.stat().st_size > max_bytes:
            result["output_limit"] = True
            with log.open("r+b") as stream:
                stream.truncate(max_bytes)
    except OSError as exc:
        result["error"] = str(exc)
        log.write_text(str(exc))
    result["seconds"] = round(time.monotonic() - start, 6)
    return result


def sandbox_prefix(cwd):
    args = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session"]
    for path in ("/usr", "/bin", "/lib", "/lib64"):
        if Path(path).exists():
            args += ["--ro-bind", path, path]
    return args + ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                   "--bind", str(Path(cwd).resolve()), "/work", "--chdir", "/work",
                   "--setenv", "HOME", "/tmp", "--"]


def sandbox_available():
    if not shutil.which("bwrap"):
        return False
    try:
        p = subprocess.run(sandbox_prefix(Path.cwd()) + ["/bin/true"],
                           capture_output=True, timeout=10)
        return p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
