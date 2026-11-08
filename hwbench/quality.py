"""Non-functional RTL quality of functional PASS copies. Never changes task PASS.

Yosys and Verilator are optional here. A missing tool yields not_run, not a clean result.
Rejection by an open-source frontend can be a tool limitation, so it is not reported as bad RTL.
"""
from collections import Counter
import difflib
import json
from pathlib import Path
import re
import shutil
import tempfile

from .common import digest, execute, sandbox_available, sandbox_prefix, task_base, tool_version, within, write_json
from .reporting import validate, write_csv

LATCH_CELLS = {"$dlatch", "$adlatch", "$dlatchsr", "$sr"}
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C"}
YOSYS_SCRIPT = "read_verilog -sv {files}; hierarchy -auto-top; proc; flatten; check; write_json netlist.json"
VERILATOR_ARGS = ["--lint-only", "-Wall", "-Wno-fatal"]


def code_lines(text):
    clean = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    return [line.strip() for line in clean.splitlines() if line.strip()]


def patch_size(starter, submitted):
    """Added plus removed non-blank code lines, ignoring comments and indentation."""
    a, b = code_lines(starter), code_lines(submitted)
    diff = difflib.ndiff(a, b)
    return sum(line[:2] in ("+ ", "- ") for line in diff)


def usable(name):
    path = shutil.which(name)
    return path and any(Path(path).resolve().is_relative_to(p) for p in (Path("/usr"), Path("/bin")))


def run_yosys(work, files, prefix, log):
    if not usable("yosys"):
        return {"status": "not_run", "reason": "yosys unavailable"}
    script = YOSYS_SCRIPT.replace("{files}", " ".join(files))
    record = execute(prefix + ["yosys", "-p", script], work, log, 60, ENV)
    text = Path(log).read_text(errors="replace")
    netlist = work / "netlist.json"
    if record.get("error") or record["timeout"] or record["returncode"] != 0 or not netlist.is_file():
        return {"status": "tool_rejected", "reason": "yosys could not elaborate; may be a frontend limitation"}
    data = json.loads(netlist.read_text())
    latches = sum(cell["type"] in LATCH_CELLS for module in data["modules"].values() for cell in module["cells"].values())
    loops = len(re.findall(r"found logic loop", text))
    status = "comb_loop" if loops else "latch_inferred" if latches else "clean"
    return {"status": status, "latches": latches, "comb_loops": loops}


def run_verilator(work, files, prefix, log):
    if not usable("verilator"):
        return {"status": "not_run", "reason": "verilator unavailable"}
    record = execute(prefix + ["verilator", *VERILATOR_ARGS, *files], work, log, 60, ENV)
    text = Path(log).read_text(errors="replace")
    if record.get("error") or record["timeout"] or record["returncode"] != 0 or re.search(r"^%Error", text, flags=re.M):
        return {"status": "tool_rejected", "reason": "verilator could not parse; may be a frontend limitation"}
    warnings = Counter(re.findall(r"^%Warning-([A-Z0-9_]+):", text, flags=re.M))
    return {"status": "clean" if not warnings else "warnings", "warnings": sum(warnings.values()), "by_type": dict(sorted(warnings.items()))}


def analyze(results, suite, out, sandbox="auto"):
    source = Path(results).resolve()
    result = validate(json.loads((source / "results.json").read_text()))
    if result.get("suite_fingerprint") != suite["fingerprint"]:
        raise ValueError("Suite fingerprint differs from the result being analyzed")
    out = Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("Quality output must be new or empty")
    out.mkdir(parents=True, exist_ok=True)
    available = sandbox_available() if sandbox != "off" else False
    if sandbox == "required" and not available:
        raise ValueError("Required bubblewrap sandbox is unavailable")
    tasks = {t["id"]: t for t in suite["tasks"]}
    passing = [r for r in result["tasks"] if r["status"] == "pass" and r.get("backend", "native") == "native"]
    rows = []
    for row in passing:
        task = tasks[row["task_id"]]
        key = f"{row['task_id']}-r{row.get('repeat', 1)}" if row.get("agent") else row["task_id"]
        snapshot = within(source, f"tasks/{key}/submission")
        texts = {name: within(snapshot, name).read_text() for name in task["files"]}
        for name, text in texts.items():
            if digest(text.encode()) != row["source_hashes"].get(name):
                raise ValueError(f"Submission copy hash mismatch: {key}/{name}")
        patch = None
        if task.get("category") == "repair":
            base = task_base(suite, task)
            patch = sum(patch_size(within(base / "starter", n).read_text(), t) for n, t in texts.items())
        with tempfile.TemporaryDirectory(prefix="hwbench-quality-") as tmp:
            work = Path(tmp)
            for name, text in texts.items():
                p = work / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text)
            prefix = sandbox_prefix(work) if available else []
            logs = out / "logs" / key
            yosys = run_yosys(work, task["files"], prefix, logs / "yosys.log")
            verilator = run_verilator(work, task["files"], prefix, logs / "verilator.log")
        rows.append({"task_id": row["task_id"], "repeat": row.get("repeat", 1), "category": row.get("category"),
                     "tier": row.get("tier", "unknown"), "code_lines": sum(len(code_lines(t)) for t in texts.values()),
                     "patch_lines": patch, "yosys": yosys, "verilator": verilator})
    report = {"schema_version": 1, "kind": "rtl_quality", "label": result["label"], "suite_fingerprint": suite["fingerprint"],
              "tools": {name: tool_version(name) for name in ("yosys", "verilator")},
              "commands": {"yosys": YOSYS_SCRIPT, "verilator": VERILATOR_ARGS},
              "protocol_fingerprint": result["protocol_fingerprint"], "planned_runs": result["planned_runs"],
              "functional_pass_runs": len(passing), "sandbox": available,
              "yosys_status": dict(Counter(r["yosys"]["status"] for r in rows)),
              "verilator_status": dict(Counter(r["verilator"]["status"] for r in rows)),
              "repair_patch_lines": _mean([r["patch_lines"] for r in rows if r["patch_lines"] is not None]),
              "verilator_warnings": _mean([r["verilator"]["warnings"] for r in rows if "warnings" in r["verilator"]]),
              "notes": ["Measured only on functional PASS copies; failed runs have no quality value, not a zero.",
                        "tool_rejected may be an open-source frontend limitation and is not a design verdict.",
                        "Open-source lint/synthesis checks are not the site lint or PPA flow."],
              "runs": rows}
    write_json(out / "quality.json", report)
    write_csv(out / "quality.csv", ["task_id", "repeat", "category", "tier", "code_lines", "patch_lines", "yosys", "latches", "comb_loops", "verilator", "lint_warnings"],
              [[r["task_id"], r["repeat"], r["category"], r["tier"], r["code_lines"], r["patch_lines"], r["yosys"]["status"], r["yosys"].get("latches"),
                r["yosys"].get("comb_loops"), r["verilator"]["status"], r["verilator"].get("warnings")] for r in rows])
    return report


def _mean(values):
    return {"observed": len(values), "mean": sum(values) / len(values) if values else None}
