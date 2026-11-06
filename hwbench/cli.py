import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile

from .common import DEFAULT_SUITE, ROOT, digest, load_suite, sandbox_available, task_base, tool_version, within, write_json
from .execution import export_suite, parse_files, run
from .grader import grade
from .reporting import compare_reports, summary, write_report
from .upstream import import_hwe


def show(result, out):
    write_report(result, out)
    s = summary(result)
    print(f"{result['label']}: {s['passed']}/{s['planned_runs']} tasks passed; infra={s['infra_errors']}")
    print(Path(out).resolve() / "report.html")


def demo(suite, out, sandbox):
    out = Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("Demo output must be empty; use a new --out")
    results = []
    for variant in ("reference", "starter", "mutant0", "mutant1"):
        with tempfile.TemporaryDirectory(prefix="hwbench-control-") as tmp:
            for t in suite["tasks"]:
                if variant.startswith("mutant"):
                    idx = int(variant[-1])
                    if len(t.get("mutants", [])) <= idx:
                        raise ValueError(f"Two mutants required for demo: {t['id']}")
                    src = t["mutants"][idx]["path"]
                else:
                    src = variant
                for name in t["files"]:
                    p = Path(tmp) / t["id"] / name
                    p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(within(task_base(suite, t), src + "/" + name), p)
            dest = out / variant
            r = grade(suite, tmp, dest, label=f"{suite['id']} / {variant}",
                      kind="fixture_" + variant, sandbox=sandbox)
            show(r, dest)
            if variant == "reference":
                if not all(t["status"] == "pass" for t in r["tasks"]):
                    raise ValueError("REFERENCE VALIDATION FAILED; do not use this benchmark")
            else:
                if any(t["status"] != "fail" for t in r["tasks"]):
                    raise ValueError(f"Negative control not functionally rejected: {variant}")
                if variant.startswith("mutant"):
                    for t, row in zip(suite["tasks"], r["tasks"]):
                        expected = t["mutants"][int(variant[-1])]["expected_fail_checks"]
                        for cid in expected:
                            checks = [c for c in row["checks"] if c["id"] == cid]
                            if not checks or not all(c["status"] == "fail" and c.get("simulation", {}).get("returncode", 0) != 0
                                                     and c["compile"]["returncode"] == 0 for c in checks):
                                raise ValueError(f"Mutant failed for the wrong reason: {t['id']}/{cid}")
            results.append(dest)
    compare_reports(results, out)
    write_json(out / "validation.json", {"status": "pass", "suite_fingerprint": suite["fingerprint"],
                                        "references_passed": len(suite["tasks"]),
                                        "mutants_detected": 2 * len(suite["tasks"]),
                                        "real_model_evaluated": False,
                                        "seeds": [1, 7, 42]})


def bundle(out):
    out = Path(out).resolve()
    if out.exists():
        raise ValueError("Bundle already exists")
    include = ["hwbench", "benchmarks", "tests", "scripts", "configs", "third_party", "docs",
               "README.md", "AGENTS.md", "pyproject.toml", ".gitignore"]
    files = []
    for name in include:
        p = ROOT / name
        if p.is_file(): files.append(p)
        elif p.is_dir(): files.extend(f for f in p.rglob("*") if f.is_file() and not f.is_symlink()
                                    and "__pycache__" not in f.parts and ".goalbuddy-board" not in f.parts)
    from .repository import file_hash
    hashes = {str(p.relative_to(ROOT)): file_hash(p) for p in sorted(files)}
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as tar:
        for p in sorted(files):
            tar.add(p, arcname=str(p.relative_to(ROOT)), recursive=False)
        raw = (json.dumps(hashes, indent=2) + "\n").encode()
        info = tarfile.TarInfo("BUNDLE_SHA256.json"); info.size = len(raw)
        tar.addfile(info, io.BytesIO(raw))
    print(f"{out}\nsha256={file_hash(out)}\nSource bundle only; simulator binaries and commercial EDA are not included.")


def verify_bundle(path):
    with tarfile.open(path, "r:gz") as tar:
        members = tar.getmembers()
        names = [m.name for m in members]
        if len(set(names)) != len(names):
            raise ValueError("Duplicate archive members")
        for m in members:
            if not m.isfile() or m.name.startswith("/") or ".." in Path(m.name).parts:
                raise ValueError("Unsafe bundle member")
        hashes = json.load(tar.extractfile("BUNDLE_SHA256.json"))
        if set(hashes) != set(names) - {"BUNDLE_SHA256.json"}:
            raise ValueError("Bundle membership mismatch")
        for name, expected in hashes.items():
            from .offline import stream_hash
            if stream_hash(tar.extractfile(name)) != expected:
                raise ValueError(f"Bundle hash mismatch: {name}")
    print(f"Bundle verified: {len(hashes)} files")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Portable HW benchmark: export, grade, run, report")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    for name in ("list", "export", "grade", "demo", "run", "import-files"):
        p = sub.add_parser(name)
        p.add_argument("--suite", default=str(DEFAULT_SUITE))
        p.add_argument("--tasks", help="Comma separated fixed subset of task IDs")
        if name != "list": p.add_argument("--out", required=True)
        if name in ("grade", "demo", "run"):
            p.add_argument("--sandbox", choices=("auto", "required", "off"), default="auto")
        if name in ("grade", "run"):
            p.add_argument("--seeds", default="1,7,42")
            p.add_argument("--check-timeout", type=float, default=10)
        if name == "grade":
            p.add_argument("--submissions", required=True)
            p.add_argument("--label", default="manual-submission")
        if name == "run":
            p.add_argument("--config", required=True)
            p.add_argument("--repeats", type=int, default=1)
            p.add_argument("--agent-timeout", type=float, default=300)
        if name == "import-files": p.add_argument("--responses", required=True)
    p = sub.add_parser("report"); p.add_argument("results");p.add_argument("--out")
    p = sub.add_parser("compare");p.add_argument("results", nargs="+");p.add_argument("--out", required=True)
    p = sub.add_parser("import-hwe");p.add_argument("final_report");p.add_argument("--out", required=True)
    p.add_argument("--label", required=True);p.add_argument("--dataset-id", required=True)
    p.add_argument("--expected-ids", help="JSON list of IDs from the pinned dataset")
    p = sub.add_parser("bundle");p.add_argument("--out", required=True)
    p = sub.add_parser("verify-bundle");p.add_argument("archive")
    p = sub.add_parser("cvdp-catalog"); p.add_argument("--datasets", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("cvdp-prepare"); p.add_argument("--dataset", required=True); p.add_argument("--bundles", required=True)
    p.add_argument("--tasks"); p.add_argument("--out", required=True)
    for name in ("repo-export", "repo-submit", "repo-grade", "repo-run", "repo-evaluate", "cvdp-import"):
        p = sub.add_parser(name); p.add_argument("--prepared", required=True); p.add_argument("--out", required=True)
        if name in ("repo-submit", "repo-grade"): p.add_argument("--submissions", required=True)
        if name == "repo-grade":
            p.add_argument("--checks", required=True); p.add_argument("--sandbox", choices=("required", "auto", "off"), default="required")
        if name == "repo-evaluate":
            p.add_argument("--kit"); p.add_argument("--profile", default="heavy")
        if name in ("repo-run", "repo-evaluate"):
            p.add_argument("--config", required=True); p.add_argument("--timeout", type=float, default=300 if name == "repo-run" else 3600)
        if name in ("repo-evaluate", "cvdp-import"): p.add_argument("--submission", required=True)
        if name == "cvdp-import": p.add_argument("--response", required=True)
    p = sub.add_parser("eda-plan"); p.add_argument("results"); p.add_argument("--config", required=True); p.add_argument("--out", required=True)
    p.add_argument("--timeout", type=float, default=3600); p.add_argument("--budget", type=float, default=14400)
    p = sub.add_parser("eda-run"); p.add_argument("queue"); p.add_argument("--cache"); p.add_argument("--max-jobs", type=int); p.add_argument("--kit"); p.add_argument("--profile", default="eda")
    p = sub.add_parser("eda-recover"); p.add_argument("queue"); p.add_argument("--retry", action="store_true")
    for name in ("eda-export", "eda-report"):
        p = sub.add_parser(name); p.add_argument("queue"); p.add_argument("--out", required=True)
    p = sub.add_parser("eda-verify-transfer"); p.add_argument("transfer")
    p = sub.add_parser("eda-import"); p.add_argument("queue"); p.add_argument("transfer")
    p = sub.add_parser("eda-compare"); p.add_argument("baseline"); p.add_argument("candidate"); p.add_argument("--out", required=True)
    p = sub.add_parser("offline-pack"); p.add_argument("--spec", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("offline-verify"); p.add_argument("kit"); p.add_argument("--profile")
    for name in ("repo-transfer", "repo-verify-transfer"):
        p = sub.add_parser(name)
        if name == "repo-transfer":
            p.add_argument("--prepared", required=True); p.add_argument("--submission", required=True)
            p.add_argument("--evaluation", required=True); p.add_argument("--out", required=True)
        else: p.add_argument("transfer")
    args = parser.parse_args(argv)
    try:
        if args.cmd.startswith("offline-"):
            from . import offline
            value = offline.pack(args.spec, args.out) if args.cmd == "offline-pack" else offline.verify(args.kit, args.profile)
            print(json.dumps(value if args.cmd == "offline-verify" else {"fingerprint": value["fingerprint"]}, indent=2)); return 0
        if args.cmd in ("repo-transfer", "repo-verify-transfer"):
            from . import repository
            value = repository.transfer(args.prepared, args.submission, args.evaluation, args.out) if args.cmd == "repo-transfer" else repository.verify_transfer(args.transfer)
            print(json.dumps(value, indent=2)); return 0
        if args.cmd.startswith("eda-"):
            from . import eda
            if args.cmd == "eda-plan": eda.plan(args.results, args.config, args.out, args.timeout, args.budget)
            elif args.cmd == "eda-run":
                q = eda.run(args.queue, args.cache, args.max_jobs, args.kit, args.profile)
                return 1 if any(j["status"] in eda.TERMINAL - {"complete"} for j in q["jobs"]) else 0
            elif args.cmd == "eda-recover": eda.recover(args.queue, args.retry)
            elif args.cmd == "eda-export": eda.export(args.queue, args.out)
            elif args.cmd == "eda-verify-transfer": eda.verify_transfer(args.transfer)
            elif args.cmd == "eda-import": eda.import_results(args.queue, args.transfer)
            elif args.cmd == "eda-report": eda.report(args.queue, args.out)
            else: eda.compare(args.baseline, args.candidate, args.out)
            return 0
        if args.cmd in {"cvdp-catalog", "cvdp-prepare", "repo-export", "repo-submit", "repo-grade", "repo-run", "repo-evaluate", "cvdp-import"}:
            from . import repository
            if args.cmd == "cvdp-catalog": repository.catalog(args.datasets, args.out)
            elif args.cmd == "cvdp-prepare": repository.prepare(args.dataset, args.bundles, args.out, args.tasks.split(",") if args.tasks else None)
            elif args.cmd == "repo-export": repository.export(args.prepared, args.out)
            elif args.cmd == "repo-submit": repository.snapshot(args.prepared, args.submissions, args.out)
            elif args.cmd == "repo-grade":
                result = repository.grade_control(args.prepared, args.submissions, args.checks, args.out, args.sandbox)
                return 0 if all(t["status"] == "pass" for t in result["tasks"]) else 1
            elif args.cmd == "repo-run":
                records = repository.run_agent(args.prepared, args.config, args.out, args.timeout)
                return 0 if all(r["returncode"] == 0 and not r["timeout"] and not r["output_limit"] and not r.get("error") for r in records) else 1
            elif args.cmd == "repo-evaluate": repository.evaluate_external(args.prepared, args.submission, args.config, args.out, args.timeout, args.kit, args.profile)
            else: repository.import_evaluation(args.prepared, args.submission, args.response, args.out)
            print(Path(args.out).resolve()); return 0
        if args.cmd == "doctor":
            tools = {x: tool_version(x) for x in ("iverilog", "vvp", "verilator", "yosys")}
            print(json.dumps({"python": sys.version, "tools": tools, "grading_sandbox_available": sandbox_available(),
                              "agent_isolation": "not provided; use separate host/container for blind evaluation",
                              "runtime_python_dependencies": "standard library only"}, indent=2))
            return 0 if tools["iverilog"]["available"] and tools["vvp"]["available"] else 2
        if args.cmd == "bundle": bundle(args.out);return 0
        if args.cmd == "verify-bundle": verify_bundle(args.archive);return 0
        if args.cmd == "report":
            p = Path(args.results);p = p / "results.json" if p.is_dir() else p
            result = json.loads(p.read_text())
            write_report(result, args.out or p.parent, source_root=p.parent)
            print(Path(args.out or p.parent).resolve() / 'report.html');return 0
        if args.cmd == "compare": compare_reports(args.results, args.out);return 0
        if args.cmd == "import-hwe":
            expected = json.loads(Path(args.expected_ids).read_text()) if args.expected_ids else None
            if expected is not None and (not isinstance(expected, list) or not all(isinstance(x, str) for x in expected) or len(set(expected)) != len(expected)):
                raise ValueError("Expected IDs must be a unique string list")
            result = import_hwe(args.final_report, args.out, args.label, args.dataset_id, expected)
            show(result, args.out);return 0
        suite = load_suite(args.suite)
        if args.tasks:
            ids = args.tasks.split(",")
            if len(ids) != len(set(ids)) or set(ids) - {t["id"] for t in suite["tasks"]}:
                raise ValueError("Unknown or duplicated selected task")
            suite["tasks"] = [t for t in suite["tasks"] if t["id"] in ids]
            suite["fingerprint"] = digest((suite["fingerprint"] + json.dumps(sorted(ids))).encode())
        if args.cmd == "list":
            for t in suite["tasks"]: print(f"{t['id']:24} {t['category']:12} {len(t['checks'])} checks | {t['title']}")
            return 0
        if args.cmd == "export": export_suite(suite, args.out);print(Path(args.out).resolve());return 0
        if args.cmd == "demo": demo(suite, args.out, args.sandbox);return 0
        if args.cmd == "import-files":
            target = Path(args.out)
            if target.exists() and any(target.iterdir()): raise ValueError("Import destination must be empty")
            rows = [json.loads(line) for line in Path(args.responses).read_text().splitlines() if line.strip()]
            byid = {r["id"]: r for r in rows}
            if len(byid) != len(rows) or set(byid) != {t["id"] for t in suite["tasks"]}:
                raise ValueError("Response IDs must exactly match selected tasks")
            payloads = {}
            for t in suite["tasks"]:
                payloads[t["id"]] = parse_files(json.dumps({"files": byid[t["id"]]["files"]}), t["files"])
            for tid, files in payloads.items():
                for name, content in files.items():
                    dest = within(target / tid, name);dest.parent.mkdir(parents=True, exist_ok=True);dest.write_text(content)
            return 0
        seeds = [int(x) for x in args.seeds.split(",")]
        if not seeds or len(set(seeds)) != len(seeds) or any(x < 0 or x > 2**31-1 for x in seeds) or not math.isfinite(args.check_timeout) or args.check_timeout <= 0:
            raise ValueError("Require distinct 31-bit nonnegative seeds and positive timeout")
        if args.cmd == "grade":
            result = grade(suite, args.submissions, args.out, args.label, seeds=seeds,
                           timeout=args.check_timeout, sandbox=args.sandbox)
        else:
            config = json.loads(Path(args.config).read_text())
            if "api_key" in config: raise ValueError("Use api_key_env, not a literal API key")
            result = run(suite, config, args.out, args.repeats, seeds, args.check_timeout,
                         args.agent_timeout, args.sandbox)
        show(result, args.out)
        return 0 if all(t["status"] == "pass" for t in result["tasks"]) else 1
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print(f"hwbench: {exc}", file=sys.stderr)
        return 2
