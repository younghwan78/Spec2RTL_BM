import datetime
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import time
import uuid

from . import __version__
from .common import (canonical, digest, execute, portable_logs, sandbox_available, sandbox_prefix,
                     task_base, tool_version, within, write_json)


def inspect_rtl(text):
    """Integrity checks, not a proof of security against adversarial HDL."""
    clean = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    for name in re.findall(r"\$([A-Za-z_][A-Za-z0-9_$]*)", clean):
        if name not in {"clog2", "bits", "signed", "unsigned"}:
            raise ValueError(f"Disallowed RTL system task/function: ${name}")
    if re.search(r"`\s*(include|define|undef|ifdef|ifndef|elsif|else|endif|line)\b", clean):
        raise ValueError("Candidate preprocessor directives are not allowed in this starter suite")
    if re.search(r"\b(force|release|bind)\b|\b(tb|testbench)\s*\.", clean):
        raise ValueError("Candidate must not control or reference the testbench")
    if re.search(r"\bmodule\s+(tb|testbench)\b", clean):
        raise ValueError("Reserved testbench module")


def grade_task(suite, task, candidate, out, seeds, timeout=10, sandbox=False):
    start = time.monotonic()
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = {"task_id": task["id"], "title": task["title"], "category": task["category"],
              "difficulty": task.get("difficulty", "unknown"), "backend": "native",
              "failure_phase": "submission", "status": "fail", "reason": "", "checks": [], "source_hashes": {},
              "required_checks": len(task["checks"]) * len(seeds), "seeds": seeds}
    texts = {}
    try:
        if Path(candidate).is_symlink():
            raise ValueError("Submission root is a symlink")
        for name in task["files"]:
            p = within(candidate, name)
            if not p.is_file():
                raise ValueError(f"Missing submission file: {name}")
            if p.stat().st_size > 1_000_000:
                raise ValueError(f"Oversized source: {name}")
            text = p.read_text()
            inspect_rtl(text)
            texts[name] = text
            result["source_hashes"][name] = digest(text.encode())
    except (ValueError, OSError, UnicodeError) as exc:
        result.update(status="invalid_submission", reason=str(exc))
        result["seconds"] = round(time.monotonic() - start, 6)
        write_json(out / "task.json", result)
        return result
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        result.update(status="infra_error", failure_phase="setup", reason="iverilog/vvp missing")
        result["seconds"] = round(time.monotonic() - start, 6)
        write_json(out / "task.json", result)
        return result
    if sandbox:
        # Sandbox mounts standard tool directories, not arbitrary user installations.
        for name in ("iverilog", "vvp"):
            executable = Path(shutil.which(name)).resolve()
            if not any(executable.is_relative_to(p) for p in (Path('/usr'), Path('/bin'), Path('/lib'), Path('/lib64'))):
                result.update(status="infra_error", failure_phase="setup", reason=f"Sandbox cannot access simulator: {name}")
                result["seconds"] = round(time.monotonic() - start, 6)
                write_json(out / "task.json", result)
                return result
    # Snapshot and hash the actual scored files; no stale workspace binaries/tests.
    for name, text in texts.items():
        p = out / "submission" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    base = task_base(suite, task)
    for check in task["checks"]:
        with tempfile.TemporaryDirectory(prefix="hwbench-grade-") as tmp:
            work = Path(tmp)
            for name, text in texts.items():
                p = work / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text)
            marker = "HWBENCH_OK_" + uuid.uuid4().hex
            tb = within(base, check["tb"]).read_text()
            if tb.count("HWBENCH_PASS") != 1:
                raise ValueError(f"Checker must have exactly one completion marker: {check['id']}")
            (work / "trusted_tb.sv").write_text(tb.replace("HWBENCH_PASS", marker))
            prefix = sandbox_prefix(work) if sandbox else []
            # A minimal environment keeps credentials and user-installed search paths out.
            env = {"PATH": "/usr/bin:/bin", "HOME": str(work), "LANG": "C"}
            compile_cmd = prefix + [shutil.which("iverilog"), "-g2012", "-s", check.get("top", "tb"),
                                    "-o", "sim.vvp", *task["files"], "trusted_tb.sv"]
            compiled = execute(compile_cmd, work, out / f"{check['id']}.compile.log", timeout, env)
            for seed in seeds:
                item = {"id": check["id"], "description": check.get("description", ""),
                        "seed": seed, "compile": compiled, "status": "fail", "completion_verified": False,
                        "failure_phase": "compile"}
                if compiled.get("error"):
                    item.update(status="infra_error", reason=compiled["error"])
                elif compiled["returncode"] != 0 or compiled["timeout"] or compiled["output_limit"]:
                    output = Path(compiled["log"]).read_text(errors="replace")
                    if sandbox and ("bwrap:" in output or "error while loading shared libraries" in output):
                        item.update(status="infra_error", reason="sandbox/tool launch failure")
                    else:
                        item["reason"] = "compile_timeout" if compiled["timeout"] else "compile_error"
                else:
                    sim = execute(prefix + [shutil.which("vvp"), "sim.vvp", f"+SEED={seed}"], work,
                                  out / f"{check['id']}.seed{seed}.log", timeout, env)
                    item["simulation"] = sim
                    item["failure_phase"] = "simulation"
                    lines = Path(sim["log"]).read_text(errors="replace").splitlines()
                    count = sum(line.strip() == marker for line in lines)
                    item["completion_verified"] = count == 1
                    if sim.get("error"):
                        item.update(status="infra_error", reason=sim["error"])
                    elif sim["returncode"] == 0 and not sim["timeout"] and not sim["output_limit"] and count == 1:
                        item.update(status="pass", failure_phase="none", reason="all assertions and completion marker passed")
                    else:
                        item["reason"] = ("simulation_timeout" if sim["timeout"] else
                                          "output_limit" if sim["output_limit"] else
                                          "assertion_or_completion_failure")
                result["checks"].append(item)
    statuses = [c["status"] for c in result["checks"]]
    if len(statuses) == result["required_checks"] and all(x == "pass" for x in statuses):
        result.update(status="pass", reason="All required checks and seeds passed")
    elif "infra_error" in statuses:
        result.update(status="infra_error", reason="Infrastructure failure; score incomplete")
    else:
        result.update(status="fail", reason="One or more required checks failed")
    phases = {c["failure_phase"] for c in result["checks"] if c["status"] != "pass"}
    result["failure_phase"] = "none" if not phases else next(iter(phases)) if len(phases) == 1 else "multiple"
    result["seconds"] = round(time.monotonic() - start, 6)
    write_json(out / "task.json", result)
    return result


def task_plan(suite, repeats=1):
    """Plan identities are independent of checker seeds and survive interrupted runs."""
    return [{"task_id": t["id"], "repeat": repeat, "category": t.get("category", "unknown"),
             "difficulty": t.get("difficulty", "unknown"), "backend": "native"}
            for repeat in range(1, repeats + 1) for t in suite["tasks"]]


def new_result(suite, label, kind, seeds, timeout, sandbox, metadata=None):
    tools = {x: tool_version(x) for x in ("iverilog", "vvp", "verilator", "yosys")}
    settings = {"suite_fingerprint": suite["fingerprint"], "seeds": seeds,
                "check_timeout_seconds": timeout, "runner_version": __version__,
                "runner_sha256": digest(b"".join(p.read_bytes() for p in sorted(Path(__file__).parent.glob("*.py")))),
                "simulator": tools["iverilog"], "sandbox": sandbox}
    return {"schema_version": 1, "run_id": uuid.uuid4().hex[:12], "label": label,
            "kind": kind, "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "suite_id": suite["id"], "origin": suite.get("origin", "unknown"),
            "suite_fingerprint": suite["fingerprint"], "file_hashes": suite["file_hashes"],
            "protocol": settings, "protocol_fingerprint": digest(canonical(settings)),
            "tools": tools, "metadata": metadata or {}, "tasks": [],
            "limitations": ["Finite simulation checks do not prove full RTL correctness.",
                            "Authored/adapted subset results are not official CVDP or HWE scores.",
                            "No commercial EDA, PPA or formal signoff was performed.",
                            "The configured agent command is not automatically sandboxed.",
                            "HDL integrity checks do not prove resistance to adversarial submissions."]}


def grade(suite, submissions, out, label="submission", kind="submission", seeds=None,
          timeout=10, sandbox="auto", metadata=None):
    seeds = seeds or [1, 7, 42]
    if not math.isfinite(timeout) or timeout <= 0 or len(set(seeds)) != len(seeds):
        raise ValueError("Require positive timeout and distinct seeds")
    out = Path(out).resolve()
    if (out / "results.json").exists():
        raise ValueError(f"Refusing to overwrite results: {out}")
    available = sandbox_available() if sandbox != "off" else False
    if sandbox == "required" and not available:
        raise ValueError("Required bubblewrap sandbox is unavailable")
    r = new_result(suite, label, kind, seeds, timeout, available, metadata)
    r["planned_runs"] = len(suite["tasks"])
    r["task_count"] = len(suite["tasks"])
    r["repeats"] = 1
    r["task_plan"] = task_plan(suite)
    write_json(out / "results.json", r)
    for t in suite["tasks"]:
        row = grade_task(suite, t, Path(submissions) / t["id"], out / "tasks" / t["id"],
                         seeds, timeout, available)
        row["repeat"] = 1
        portable_logs(row, out)
        r["tasks"].append(row)
        write_json(out / "results.json", r)
    return r
