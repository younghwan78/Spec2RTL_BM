#!/usr/bin/env python3
"""Convert pre-downloaded VerilogEval and RTLLM checkouts into offline native suites.

Run outside the closed network, once, from pinned checkouts. Nothing is downloaded here.
This generator overwrites only directories it is explicitly given with --force; do not run it
for routine validation. Every kept task is gated by real simulation:
reference passes on all seeds, stub starter fails, and generated mutants compile and are killed
on all seeds. Tasks that do not meet the gate are recorded as excluded, not silently dropped.
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hwbench.checker_audit import audit_design  # noqa: E402
from hwbench.common import sandbox_available, sandbox_prefix  # noqa: E402
from hwbench.grader import inspect_rtl  # noqa: E402

SEEDS = [1, 7, 42]
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C"}
MARKER = "HWBENCH_PASS"
SIM_LIMIT = 8
MAX_ATTEMPTS = 40
WANT_KILLED = 3


def sha(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def run(work, argv, sandbox, timeout):
    prefix = sandbox_prefix(work) if sandbox else []
    try:
        p = subprocess.run(prefix + argv, cwd=work, env=ENV, capture_output=True, text=True,
                           errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)
        return p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return None, ""


def simulate(files, tb, top, seeds, sandbox):
    """Same compile order and pass rule as the grader: task files first, then the trusted bench."""
    with tempfile.TemporaryDirectory(prefix="hwb-import-") as tmp:
        work = Path(tmp)
        for name, text in files.items():
            p = work / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        (work / "trusted_tb.sv").write_text(tb)
        rc, out = run(work, ["iverilog", "-g2012", "-s", top, "-o", "sim.vvp", *files, "trusted_tb.sv"], sandbox, 30)
        if rc != 0:
            return ["compile_error"] * len(seeds), out
        states = []
        for seed in seeds:
            rc, out = run(work, ["vvp", "sim.vvp", f"+SEED={seed}"], sandbox, SIM_LIMIT)
            lines = [line.strip() for line in out.splitlines()]
            if rc is None:
                states.append("timeout")
            elif rc == 0 and lines.count(MARKER) == 1:
                states.append("pass")
            elif rc != 0:
                states.append("functional")
            else:
                states.append("no_marker")
        return states, out


def strip_comments(text):
    return re.sub(r"/\*.*?\*/|//[^\n]*", lambda m: " " * len(m[0]), text, flags=re.S)


def balanced(text, start):
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return None


BINOPS = [("and_or", r"(?<=\s)&(?=\s)", "|"), ("or_and", r"(?<=\s)\|(?=\s)", "&"),
          ("land_lor", r"&&", "||"), ("lor_land", r"\|\|", "&&"),
          ("add_sub", r"(?<=\s)\+(?=\s)", "-"), ("sub_add", r"(?<=\s)-(?=\s)", "+"),
          ("xor_and", r"(?<=\s)\^(?=\s)", "&"), ("eq_ne", r"==", "!="), ("ne_eq", r"!=", "=="),
          ("lt_gt", r"(?<=\s)<(?=\s)", ">"), ("gt_lt", r"(?<=\s)>(?=\s)", "<"),
          ("ge_gt", r">=", ">"), ("shl_shr", r"<<", ">>"), ("shr_shl", r">>", "<<"),
          ("drop_not", r"~(?=[A-Za-z_(])", ""),
          ("const_0_1", r"1'b0", "1'b1"), ("const_1_0", r"1'b1", "1'b0"),
          ("nba_const", r"(?<=<=)\s*0\s*;", " 1;")]


def candidates(text):
    """Deterministic mutation list, round-robin across operator classes for diversity."""
    code = strip_comments(text)
    body = code.find(");")
    body = body if body >= 0 else 0
    classes = {}
    for name, pat, rep in BINOPS:
        for m in re.finditer(pat, code):
            if m.start() > body:
                classes.setdefault(name, []).append((m.start(), m.end(), rep))
    for m in re.finditer(r"\bif\s*\(", code):
        close = balanced(code, m.end() - 1)
        if close:
            classes.setdefault("if_negate", []).append(
                (m.end(), close, "!(" + text[m.end():close] + ")"))
    for m in re.finditer(r"\bassign\s+[^=;]+=\s*([^;]+);", code):
        classes.setdefault("assign_invert", []).append(
            (m.start(1), m.end(1), "~(" + text[m.start(1):m.end(1)] + ")"))
    # Procedural right-hand sides, excluding assign, parameters, for-loop headers and declarations.
    for m in re.finditer(r"(?m)(?<![=!<>])(?:<=|=)(?!=)\s*([^;=]+);", code):
        line = code[code.rfind("\n", 0, m.start()) + 1:m.start()]
        if m.start() > body and not re.search(r"\b(assign|parameter|localparam|for|input|output|wire|reg|logic|integer|int)\b", line):
            classes.setdefault("rhs_invert", []).append(
                (m.start(1), m.end(1), "~(" + text[m.start(1):m.end(1)] + ")"))
    # Sized literals, the natural defect site in case tables, K-maps and truth tables.
    for m in re.finditer(r"\b\d+'[bdh][0-9a-fA-F]+", code):
        if m.start() > body:
            last = code[m.end() - 1]
            classes.setdefault("literal_flip", []).append((m.end() - 1, m.end(), "0" if last != "0" else "1"))
    order = sorted(classes)
    out = []
    index = 0
    while any(index < len(classes[k]) for k in order):
        for name in order:
            if index < len(classes[name]):
                start, end, rep = classes[name][index]
                out.append((f"{name}_{index}", text[:start] + rep + text[end:]))
        index += 1
    return out


def find_mutants(files_key, reference, tb, top, sandbox, others):
    killed = []
    for name, mutated in candidates(reference)[:MAX_ATTEMPTS]:
        try:
            inspect_rtl(mutated)
        except ValueError:
            continue
        states, _ = simulate({files_key: mutated, **others}, tb, top, SEEDS, sandbox)
        if all(s == "functional" for s in states):
            killed.append((name, mutated))
            if len(killed) >= WANT_KILLED:
                break
    return killed


def seed_inject(tb, scope):
    """Make otherwise fixed $random stimulus depend on +SEED. Returns (text, sensitive)."""
    new, a = re.subn(r"\$random\b(?!\s*\()", f"$random({scope}hwb_seed)", tb)
    new, b = re.subn(r"\$urandom\b(?!_range)(?!\s*\()", f"$unsigned($random({scope}hwb_seed))", new)
    return new, bool(a or b)


def difficulty(reference):
    loc = sum(1 for line in strip_comments(reference).splitlines() if line.strip())
    return "easy" if loc <= 10 else "medium" if loc <= 30 else "hard"


def write_task(root, tid, prompt, top_file, reference, starter, tb, mutants):
    base = root / "tasks" / tid
    for sub, text in (("reference", reference), ("starter", starter)):
        p = base / sub / top_file
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    (base / "checks").mkdir(parents=True, exist_ok=True)
    (base / "checks" / "equivalence.sv").write_text(tb)
    (base / "prompt.md").write_text(prompt)
    out = []
    for name, mutated in mutants:
        p = base / "mutants" / name / top_file
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(mutated)
        out.append({"id": name, "path": f"mutants/{name}", "expected_fail_checks": ["equivalence"]})
    return out


def task_entry(tid, category, title, top_file, mutants, top, description, meta):
    return {"id": tid, "category": category, "title": title, "path": f"tasks/{tid}", "files": [top_file],
            "checks": [{"id": "equivalence", "tb": "checks/equivalence.sv", "top": top, "description": description}],
            "mutants": mutants, **meta}


def adapt_verilog_eval(prefix, sandbox):
    name = prefix.name[: -len("_prompt.txt")]
    stem = prefix.parent / name
    ref = Path(f"{stem}_ref.sv").read_text()
    test = Path(f"{stem}_test.sv").read_text()
    number = re.match(r"Prob(\d+)_(.*)", name)
    tid = f"ve{number[1]}_{number[2]}"
    record = {"id": tid, "source": name}
    hidden = "HwbRef_" + sha(tid)[:12]
    head = re.search(r"\bmodule\s+RefModule\b.*?\);", ref, flags=re.S)
    if not head or "RefModule" not in test:
        return record | {"excluded": "unrecognized module header"}
    final = re.search(r'\$display\("Mismatches:[^\n]*\n', test)
    if not final or len(re.findall(r'\$display\("Mismatches:', test)) != 1:
        return record | {"excluded": "no unique mismatch report"}
    # The upstream #1000000 cap only truncates DUT-independent stimulus, so it is not a failure by itself.
    verdict = final[0] + ('\t\tif (stats1.errors != 0 || stats1.clocks == 0) '
                          '$fatal(1, "HWBENCH mismatch");\n\t\telse $display("HWBENCH_PASS");\n')
    tb = test.replace(final[0], verdict)
    module = re.search(r"\bmodule\s+tb\b[^;]*;", tb)
    if not module:
        return record | {"excluded": "no tb module"}
    tb = tb[:module.end()] + ('\n\tinteger hwb_seed = 1;\n'
                              '\tinitial if (!$value$plusargs("SEED=%d", hwb_seed)) hwb_seed = 1;\n') + tb[module.end():]
    tb, sensitive = seed_inject(tb, "tb.")
    tb = re.sub(r"\bRefModule\b", hidden, tb) + "\n" + re.sub(r"\bRefModule\b", hidden, ref)
    top = re.sub(r"\bRefModule\b", "TopModule", ref)
    top_file = "rtl/TopModule.sv"
    starter = re.sub(r"\bRefModule\b", "TopModule", head[0]) + "\n  // Implement the specified behaviour here.\nendmodule\n"
    states, out = simulate({top_file: top}, tb, "tb", SEEDS, sandbox)
    if states != ["pass"] * 3:
        return record | {"excluded": f"reference gate: {states}", "detail": out[-300:]}
    if "pass" in simulate({top_file: starter}, tb, "tb", SEEDS, sandbox)[0]:
        return record | {"excluded": "stub starter passes"}
    killed = find_mutants(top_file, top, tb, "tb", sandbox, {})
    if len(killed) < 2:
        return record | {"excluded": f"only {len(killed)} killable mutants found"}
    audit = audit_design({top_file: top}, "TopModule", [(tb, "tb")], SEEDS, sandbox)
    if audit["status"] != "pass":
        return record | {"excluded": f"checker audit {audit['status']}: {audit.get('reason') or audit['findings'][:4]}"}
    has_clk = re.search(r"\binput\b[^;]*\bclk\b", head[0])
    domain = "fsm" if has_clk and re.search(r"\bstate\b", ref) else "sequential" if has_clk else "combinational"
    prompt = Path(prefix).read_text().strip() + (
        "\n\nThe module must be named `TopModule`. Provide synthesizable SystemVerilog only; "
        "no testbench or simulation system tasks belong in the submitted RTL.\n")
    return record | {"tid": tid, "top": top, "tb": tb, "starter": starter, "killed": killed, "prompt": prompt,
                     "file": top_file, "tb_top": "tb", "domain": domain, "difficulty": difficulty(top),
                     "seed_sensitive": sensitive, "title": number[2].replace("_", " "),
                     "hashes": {p: sha(Path(f"{stem}_{p}").read_bytes()) for p in ("prompt.txt", "ref.sv", "test.sv")}}


RTLLM_DOMAIN = {"Arithmetic": "arithmetic", "Memory": "memory", "Control": "control", "Miscellaneous": "misc"}


def rtllm_header(text):
    """Return a compilable, body-free module header keeping port declarations."""
    code = strip_comments(text)
    start = re.search(r"\bmodule\b", code)
    end = None
    depth = 0
    for i in range(start.start(), len(code)):
        depth += code[i] == "("
        depth -= code[i] == ")"
        if code[i] == ";" and depth == 0:
            end = i + 1
            break
    head = code[start.start():end]
    decl = []
    for statement in re.finditer(r"[^;]*;", code[end:]):
        if re.match(r"\s*(input|output|inout|parameter|localparam)\b", statement[0]):
            decl.append(statement[0].strip())
        else:
            break
    return head + "\n" + "\n".join(decl)


def adapt_rtllm(tb_path, root, sandbox):
    d = tb_path.parent
    record = {"id": "rtllm_" + d.name, "source": str(d.relative_to(root))}
    refs = sorted(d.glob("verified_*"))
    description = d / "design_description.txt"
    if len(refs) != 1 or not description.is_file():
        return record | {"excluded": "reference or description missing"}
    spec = description.read_text(errors="replace")
    named = re.search(r"Module name:\s*(\w+)", spec, flags=re.I)
    if not named:
        return record | {"excluded": "module name not stated in description"}
    top_name = named[1]
    original = refs[0].read_text(errors="replace")
    modules = re.findall(r"^\s*module\s+(\w+)", strip_comments(original), flags=re.M)
    tops = [m for m in modules if m in (f"verified_{top_name}", top_name)] or (modules if len(modules) == 1 else [])
    if len(tops) != 1:
        return record | {"excluded": f"cannot identify top among {modules}"}
    reference = re.sub(rf"\b{tops[0]}\b", top_name, original)
    if not re.search(rf"\b{top_name}\b", tb_path.read_text(errors="replace")):
        return record | {"excluded": "testbench does not instantiate the documented module"}
    tb = tb_path.read_text(errors="replace")
    tb, passed = re.subn(r'\$display\s*\(\s*"=*\s*Your Design Passed\s*=*"\s*\)', '$display("HWBENCH_PASS")', tb)
    tb, failed = re.subn(r'\$display\s*\(\s*"=*\s*(Test completed|(?:Error|Failed)\s*=+")', r'$fatal(1, "\1', tb)
    if passed != 1 or failed < 1:
        return record | {"excluded": f"verdict lines passed={passed} failed={failed}"}
    module = re.search(r"\bmodule\s+(\w+)[^;]*;", strip_comments(tb))
    tb_top = module[1]
    tb, sensitive = seed_inject(tb, "")
    if sensitive:
        tb = tb[:module.end()] + ('\ninteger hwb_seed = 1;\ninitial if (!$value$plusargs("SEED=%d", hwb_seed)) hwb_seed = 1;\n'
                                  ) + tb[module.end():]
    top_file = f"rtl/{top_name}.v"
    starter = rtllm_header(reference) + "\n  // Implement the specified behaviour here.\nendmodule\n"
    states, out = simulate({top_file: reference}, tb, tb_top, SEEDS, sandbox)
    if states != ["pass"] * 3:
        return record | {"excluded": f"reference gate: {states}", "detail": out[-300:]}
    if "pass" in simulate({top_file: starter}, tb, tb_top, SEEDS, sandbox)[0]:
        return record | {"excluded": "stub starter passes"}
    killed = find_mutants(top_file, reference, tb, tb_top, sandbox, {})
    if len(killed) < 2:
        return record | {"excluded": f"only {len(killed)} killable mutants found"}
    audit = audit_design({top_file: reference}, top_name, [(tb, tb_top)], SEEDS, sandbox)
    if audit["status"] != "pass":
        return record | {"excluded": f"checker audit {audit['status']}: {audit.get('reason') or audit['findings'][:4]}"}
    area = d.relative_to(root).parts[0]
    prompt = spec.strip() + (f"\n\nThe module must be named `{top_name}`. Provide synthesizable Verilog only; "
                             "no testbench or simulation system tasks belong in the submitted RTL.\n")
    return record | {"tid": "rtllm_" + d.name, "top": reference, "tb": tb, "starter": starter, "killed": killed,
                     "prompt": prompt, "file": top_file, "tb_top": tb_top, "domain": RTLLM_DOMAIN.get(area, "misc"),
                     "difficulty": difficulty(reference), "seed_sensitive": sensitive, "title": d.name.replace("_", " "),
                     "hashes": {p.name: sha(p.read_bytes()) for p in (description, refs[0], tb_path)}}


def write_suite(root, sid, title, origin, items, tier, basis):
    tasks = []
    for it in items:
        muts = write_task(root, it["tid"], it["prompt"], it["file"], it["top"], it["starter"], it["tb"], it["killed"][:2])
        tasks.append(task_entry(it["tid"], "generation", it["title"], it["file"], muts, it["tb_top"],
                                "Hidden equivalence or directed bench from the public benchmark",
                                {"difficulty": it["difficulty"], "domain": it["domain"], "tier": tier,
                                 "seed_sensitive": it["seed_sensitive"], "tags": [tier, origin]}))
    (root / "suite.json").write_text(json.dumps({
        "schema_version": 1, "id": sid, "title": title, "origin": origin, "difficulty_basis": basis, "tasks": tasks},
        indent=2, ensure_ascii=False) + "\n")
    return tasks


REPAIR_NOTE = ("\n\nThe RTL file provided in this workspace was written for the specification above but contains "
               "a functional defect. Repair it so that it fully meets the specification. Keep the module name and "
               "ports. Do not rewrite unrelated logic.\n")


def write_repair(root, items):
    tasks = []
    for it in items:
        tid = "fix_" + it["tid"]
        (bug_name, bug_text), *others = it["killed"]
        muts = write_task(root, tid, it["prompt"] + REPAIR_NOTE, it["file"], it["top"], bug_text, it["tb"], others[:2])
        tasks.append(task_entry(tid, "repair", "repair " + it["title"], it["file"], muts, it["tb_top"],
                                "Hidden bench; starter carries one injected defect",
                                {"difficulty": it["difficulty"], "domain": it["domain"], "tier": "synthetic_repair",
                                 "seed_sensitive": it["seed_sensitive"], "injected_defect": bug_name,
                                 "tags": ["synthetic_repair", "not_a_real_bug"]}))
    (root / "suite.json").write_text(json.dumps({
        "schema_version": 1, "id": "public-synthetic-repair-v1", "title": "Injected-defect repair on public benchmark specs",
        "origin": "injected_defects_on_adapted_public_tasks", "difficulty_basis": "reference_loc_heuristic", "tasks": tasks},
        indent=2, ensure_ascii=False) + "\n")
    return tasks


def prepare_out(path, force):
    if path.exists():
        if not force:
            raise SystemExit(f"Refusing to overwrite {path}; review the diff and pass --force")
        shutil.rmtree(path)
    path.mkdir(parents=True)


def provenance(dest, source, url, license_file, rows, notes):
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(license_file, dest / "LICENSE")
    revision = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    (dest / "provenance.json").write_text(json.dumps({
        "source": url, "revision": revision, "license_file": "LICENSE", "notes": notes,
        "kept": {r["tid"]: {"source": r["source"], "sha256": r["hashes"]} for r in rows if "tid" in r},
        "excluded": [{k: v for k, v in r.items() if k in ("id", "source", "excluded", "detail")} for r in rows if "tid" not in r]},
        indent=2, ensure_ascii=False) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--verilog-eval", required=True, type=Path)
    p.add_argument("--rtllm", required=True, type=Path)
    p.add_argument("--jobs", type=int, default=6)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    sandbox = sandbox_available()
    if not sandbox:
        raise SystemExit("bubblewrap is required: upstream benches are compiled and simulated here")
    with cf.ThreadPoolExecutor(args.jobs) as ex:
        ve = list(ex.map(lambda f: adapt_verilog_eval(f, sandbox),
                         sorted((args.verilog_eval / "dataset_spec-to-rtl").glob("*_prompt.txt"))))
        benches = sorted(x for x in args.rtllm.rglob("testbench.v") if not any(s.startswith("_") for s in x.relative_to(args.rtllm).parts))
        rt = list(ex.map(lambda f: adapt_rtllm(f, args.rtllm, sandbox), benches))
    ve_ok, rt_ok = [r for r in ve if "tid" in r], [r for r in rt if "tid" in r]
    for name, title, origin, rows in (("verilog_eval", "VerilogEval spec-to-RTL (native adapted)", "verilog_eval_adapted_not_official_score", ve_ok),
                                      ("rtllm", "RTLLM 2.0 (native adapted)", "rtllm_adapted_not_official_score", rt_ok)):
        out = ROOT / "benchmarks" / name
        prepare_out(out, args.force)
        write_suite(out, name.replace("_", "-") + "-adapted-v1", title, origin, rows, "public_small", "reference_loc_heuristic")
    repair_rows = [r for r in ve_ok + rt_ok if len(r["killed"]) >= 3 and r["difficulty"] != "easy"]
    out = ROOT / "benchmarks" / "public_repair"
    prepare_out(out, args.force)
    write_repair(out, repair_rows)
    provenance(ROOT / "third_party" / "verilog_eval", args.verilog_eval, "https://github.com/NVlabs/verilog-eval",
               args.verilog_eval / "LICENSE", ve,
               "Problems derive from HDLBits. Checkers are adapted (seeded stimulus, HWBench verdict); results are not official VerilogEval scores.")
    provenance(ROOT / "third_party" / "rtllm", args.rtllm, "https://github.com/hkust-zhiyao/RTLLM", args.rtllm / "LICENSE", rt,
               "Checkers are adapted (HWBench verdict, seeded stimulus where random). Results are not official RTLLM scores.")
    print(f"verilog_eval kept={len(ve_ok)} excluded={len(ve) - len(ve_ok)}")
    print(f"rtllm kept={len(rt_ok)} excluded={len(rt) - len(rt_ok)}")
    print(f"public_repair kept={len(repair_rows)}")
    for r in ve + rt:
        if "tid" not in r:
            print("EXCLUDED", r["id"], str(r["excluded"])[:110])


if __name__ == "__main__":
    main()
