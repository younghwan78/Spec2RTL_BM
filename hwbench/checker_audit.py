"""Negative controls for checker strength, applied to a task's own reference RTL.

Mutants only show that particular defects are caught. These controls ask a different question:
would the checker accept RTL that ignores its job?

  tie:     one output is replaced by a constant the reference did not always produce.
  constant: every output is held at a value the reference produced at some point.

A control that passes means the checker cannot see that behaviour. A reference that keeps an output
constant under the bench is not penalized for that value. Constant controls are skipped only for a
module with no inputs and a single observed value, so a correct constant design still passes.
Passing this audit does not prove a checker is complete.
"""
import collections
import concurrent.futures as cf
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .common import sandbox_available, sandbox_prefix, task_base, within, write_json

ENV = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C"}
MARKER = "HWBENCH_PASS"
PROBE = "HWAUDIT"
CORE = "hwaudit_ref_core"
SIM_LIMIT = 8
MAX_CONSTANTS = 64
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*$")


class Unsupported(ValueError):
    pass


def strip_comments(text):
    return re.sub(r"/\*.*?\*/|//[^\n]*", lambda m: " " * len(m[0]), text, flags=re.S)


def module_header(text, top):
    """Header up to its semicolon, plus non-ANSI declarations when the header has no directions."""
    code = strip_comments(text)
    found = re.search(rf"\bmodule\s+{re.escape(top)}\b", code)
    if not found:
        raise Unsupported(f"module {top} not found")
    depth, end = 0, None
    for index in range(found.start(), len(code)):
        depth += code[index] == "("
        depth -= code[index] == ")"
        if code[index] == ";" and depth == 0:
            end = index + 1
            break
    if end is None:
        raise Unsupported("unterminated module header")
    head = code[found.start():end]
    decl = []
    if not re.search(r"\b(input|output|inout)\b", head):
        for statement in re.finditer(r"[^;]*;", code[end:]):
            text_part = statement[0].strip()
            if re.match(r"(always|assign|initial|function|task|endmodule)\b", text_part):
                break
            if re.match(r"(input|output|inout|parameter|localparam)\b", text_part):
                decl.append(text_part)
    return head, decl


def balanced_close(text, start):
    depth = 0
    for index in range(start, len(text)):
        depth += text[index] == "("
        depth -= text[index] == ")"
        if depth == 0:
            return index
    raise Unsupported("unbalanced parentheses in header")


def split_commas(text):
    parts, depth, current = [], 0, []
    for char in text:
        depth += char in "([{"
        depth -= char in ")]}"
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def interface(head, decl):
    """Return (parameter names, ordered [(direction, name)]) from a module header."""
    params = []
    ports_text = head
    start = re.search(r"#\s*\(", head)
    if start:
        close = balanced_close(head, start.end() - 1)
        for piece in split_commas(head[start.end():close]):
            name = re.search(r"([A-Za-z_]\w*)\s*=", piece)
            if name:
                params.append(name[1])
        ports_text = head[:start.start()] + head[close + 1:]
    for statement in decl:
        if statement.startswith("parameter"):
            for piece in split_commas(statement[len("parameter"):].rstrip(";")):
                name = re.search(r"([A-Za-z_]\w*)\s*=", piece)
                if name:
                    params.append(name[1])
    joined = ports_text + " " + " ".join(s for s in decl if not s.startswith(("parameter", "localparam")))
    ports = []
    for match in re.finditer(r"\b(input|output|inout)\b(.*?)(?=\b(?:input|output|inout)\b|\Z)", joined, flags=re.S):
        body = re.sub(r"\[[^\]]*\]", " ", match[2])
        body = re.sub(r"\b(wire|reg|logic|signed|unsigned)\b", " ", body).replace(")", " ").replace(";", " ")
        for name in body.split(","):
            name = name.strip()
            if name:
                if not IDENT.match(name):
                    raise Unsupported(f"unsupported port declaration: {name}")
                ports.append((match[1], name))
    if not any(direction == "output" for direction, _ in ports):
        raise Unsupported("no output ports found")
    return params, ports


def plain_header(head, decl):
    text = head + "\n" + "\n".join(decl)
    return re.sub(r"\b(reg|logic)\b", " ", text)


def wrapper(head, decl, params, ports, skip=(), body=""):
    overrides = (" #(" + ", ".join(f".{p}({p})" for p in params) + ")") if params else ""
    connections = ", ".join(f".{n}()" if n in skip else f".{n}({n})" for _, n in ports)
    return f"{plain_header(head, decl)}\n  {CORE}{overrides} hwaudit_u ({connections});\n{body}endmodule\n"


def run(work, argv, sandbox, timeout):
    prefix = sandbox_prefix(work) if sandbox else []
    try:
        done = subprocess.run(prefix + argv, cwd=work, env=ENV, capture_output=True, text=True, errors="replace",
                              timeout=timeout, stdin=subprocess.DEVNULL)
        return done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired:
        return None, ""


def simulate(files, checks, seeds, sandbox, keep_output=False):
    """True only when every check and seed passes, using the grader's pass rule."""
    outputs = []
    with tempfile.TemporaryDirectory(prefix="hwbench-audit-") as tmp:
        work = Path(tmp)
        for name, text in files.items():
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        for tb, top in checks:
            (work / "trusted_tb.sv").write_text(tb)
            code, _ = run(work, ["iverilog", "-g2012", "-s", top, "-o", "sim.vvp", *files, "trusted_tb.sv"], sandbox, 30)
            if code != 0:
                return False, outputs
            for seed in seeds:
                code, out = run(work, ["vvp", "sim.vvp", f"+SEED={seed}"], sandbox, SIM_LIMIT)
                if code != 0 or [line.strip() for line in out.splitlines()].count(MARKER) != 1:
                    return False, outputs
                if keep_output:
                    outputs.append(out)
    return True, outputs


def observe(outputs, width):
    per_output = [set() for _ in range(width)]
    tuples = collections.Counter()
    last = None
    for out in outputs:
        for line in out.splitlines():
            if not line.startswith(PROBE + " "):
                continue
            values = line.split()[1:]
            if len(values) != width:
                continue
            for index, value in enumerate(values):
                if set(value) <= {"0", "1"}:
                    per_output[index].add(value)
            if all(set(v) <= {"0", "1"} for v in values):
                current = tuple(values)
                tuples[current] += 1
                last = current
    return per_output, tuples, last


def audit_design(files, top, checks, seeds, sandbox):
    """files maps relative names to reference text; checks is [(bench text, bench top)]."""
    try:
        owner = next((n for n, t in files.items() if re.search(rf"\bmodule\s+{re.escape(top)}\b", strip_comments(t))), None)
        if owner is None:
            raise Unsupported(f"module {top} not found in task files")
        head, decl = module_header(files[owner], top)
        params, ports = interface(head, decl)
    except Unsupported as exc:
        return {"status": "unsupported", "reason": str(exc), "findings": [], "controls_run": 0}
    renamed = {n: re.sub(rf"\b{re.escape(top)}\b", CORE, t) for n, t in files.items()}
    outs = [n for d, n in ports if d == "output"]
    listing = ", ".join(outs)
    fmt = " ".join(["%b"] * len(outs))
    probe = (f"  always @({' or '.join(outs)}) $display(\"{PROBE} {fmt}\", {listing});\n"
             f"  final $display(\"{PROBE} {fmt}\", {listing});\n")

    def with_top(text):
        changed = dict(renamed)
        changed[owner] = changed[owner] + "\n" + text
        return changed

    passed, outputs = simulate(with_top(wrapper(head, decl, params, ports, body=probe)), checks, seeds[:1], sandbox, True)
    if not passed:
        return {"status": "unsupported", "reason": "instrumented reference did not pass", "findings": [], "controls_run": 0}
    per_output, tuples, last = observe(outputs, len(outs))
    controls = []
    for index, name in enumerate(outs):
        seen = per_output[index]
        if any("1" in value for value in seen):
            controls.append((f"tie:{name}=0", (name,), f"  assign {name} = 0;\n"))
        if any("0" in value for value in seen):
            controls.append((f"tie:{name}=1s", (name,), f"  assign {name} = -1;\n"))
    # One observed value with inputs present usually means the bench exercised one input only.
    if tuples and (len(tuples) > 1 or any(d == "input" for d, _ in ports)):
        ordered = [last] + [value for value, _ in tuples.most_common(MAX_CONSTANTS)]
        for values in list(dict.fromkeys(ordered))[:MAX_CONSTANTS]:
            body = "".join(f"  assign {n} = {len(v)}'b{v};\n" for n, v in zip(outs, values))
            controls.append(("constant:" + ",".join(values)[:60], tuple(outs), body))
    findings = []
    for label, skip, body in controls:
        passed, _ = simulate(with_top(wrapper(head, decl, params, ports, skip=skip, body=body)), checks, seeds, sandbox)
        if passed:
            findings.append(label)
    return {"status": "weak" if findings else "pass", "findings": findings, "controls_run": len(controls)}


def audit_task(suite, task, seeds, sandbox):
    base = task_base(suite, task)
    files = {name: within(base / "reference", name).read_text() for name in task["files"]}
    checks = [(within(base, c["tb"]).read_text(), c.get("top", "tb")) for c in task["checks"]]
    return {"task_id": task["id"], **audit_design(files, Path(task["files"][0]).stem, checks, seeds, sandbox)}


def audit_suite(suite, out, seeds=None, sandbox="auto", jobs=4):
    seeds = seeds or [1, 7, 42]
    out = Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("Audit output must be new or empty")
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        raise ValueError("iverilog/vvp missing")
    available = sandbox_available() if sandbox != "off" else False
    if sandbox == "required" and not available:
        raise ValueError("Required bubblewrap sandbox is unavailable")
    with cf.ThreadPoolExecutor(max(1, jobs)) as pool:
        rows = list(pool.map(lambda task: audit_task(suite, task, seeds, available), suite["tasks"]))
    counts = collections.Counter(row["status"] for row in rows)
    report = {"schema_version": 1, "kind": "checker_audit", "suite_id": suite["id"], "suite_fingerprint": suite["fingerprint"],
              "seeds": seeds, "sandbox": available, "counts": dict(counts), "tasks": rows,
              "notes": ["Passing means the bench rejected these controls; it does not prove the bench is complete.",
                        "unsupported means the audit could not be applied, so strength is unknown for that task."]}
    write_json(out / "checker_audit.json", report)
    return report
