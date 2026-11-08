#!/usr/bin/env python3
"""Generic EDA wrapper: site-specific commands and report parsing live in a JSON profile.

Usage (through eda-plan/eda-run argv): eda_profile_wrapper.py PROFILE REQUEST RESPONSE

No vendor tool name, flag or report format is assumed here. The profile says what to execute and
how to read the raw reports, so tools or versions can change without touching this file. The
profile is a queue asset, so changing it changes the PPA condition hash.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

METRICS = {"area_um2": "um^2", "delay_ns": "ns", "power_mw": "mW"}
PLACEHOLDER = "REPLACE_"


class ProfileError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_profile(path):
    text = Path(path).read_text()
    if PLACEHOLDER in text:
        raise ProfileError(f"Profile still has {PLACEHOLDER} placeholders: {path}")
    profile = json.loads(text)
    if profile.get("schema_version") != 1 or not isinstance(profile.get("steps"), list) or not profile["steps"]:
        raise ProfileError("Profile requires schema_version=1 and a nonempty steps list")
    for step in profile["steps"]:
        if not isinstance(step.get("role"), str) or not isinstance(step.get("argv"), list) or not step["argv"]:
            raise ProfileError("Each step requires role and argv")
    if set(profile.get("metrics", {})) != set(METRICS):
        raise ProfileError(f"Profile metrics must be exactly {sorted(METRICS)}")
    return profile


def safe_report(root, name):
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ProfileError(f"Report path must stay under the job directory: {name}")
    path = Path(root) / relative
    if path.is_symlink():
        raise ProfileError(f"Report is a symlink: {name}")
    return path


def read_report(root, name):
    path = safe_report(root, name)
    if not path.is_file():
        raise ProfileError(f"Missing report: {name}")
    return path.read_text(errors="replace")


def extract(rule, root, label):
    """A term is one regex capture, multiplied by scale into the normalized unit."""
    text = read_report(root, rule["report"])
    hits = re.findall(rule["regex"], text, flags=re.M)
    if not hits:
        raise ProfileError(f"{label}: regex found nothing in {rule['report']}")
    occurrence = rule.get("occurrence", -1)
    try:
        hit = hits[occurrence]
    except IndexError as exc:
        raise ProfileError(f"{label}: only {len(hits)} matches in {rule['report']}") from exc
    if isinstance(hit, tuple):
        hit = hit[rule.get("group", 0)]
    try:
        value = float(hit) * float(rule.get("scale", 1.0))
    except ValueError as exc:
        raise ProfileError(f"{label}: captured value is not numeric: {hit!r}") from exc
    if not math.isfinite(value) or value < 0:
        raise ProfileError(f"{label}: value must be finite and nonnegative: {value}")
    return value


def parse_metrics(profile, root):
    """A metric is the sum of its terms, for example dynamic plus leakage power."""
    values = {}
    for name, rule in profile["metrics"].items():
        terms = rule.get("terms")
        if not isinstance(terms, list) or not terms:
            raise ProfileError(f"{name}: terms list required")
        values[name] = sum(extract(term, root, name) for term in terms)
    return values


def parse_quality(profile, root):
    """Fail wins over pass. Neither matching is an infrastructure error, never a silent pass."""
    out = {"lint": "not_requested", "xprop": "not_requested"}
    for name, rule in profile.get("quality", {}).items():
        if name not in out:
            raise ProfileError(f"Unknown quality key: {name}")
        text = read_report(root, rule["report"])
        if re.search(rule["fail_regex"], text, flags=re.M):
            out[name] = "fail"
        elif re.search(rule["pass_regex"], text, flags=re.M):
            out[name] = "pass"
        else:
            out[name] = "infra_error"
    return out


def report_names(profile):
    names = {term["report"] for rule in profile["metrics"].values() for term in rule["terms"]}
    names |= {rule["report"] for rule in profile.get("quality", {}).values()}
    names.add(profile["activity"]["report"])
    if profile.get("license_wait"):
        names.add(profile["license_wait"]["report"])
    return sorted(names)


def substitute(arg, values):
    for key, value in values.items():
        arg = arg.replace(key, str(value))
    if re.search(r"\{(asset:[^}]*|sources|filelist|top|work|params_json|clock_period_ns|workload_id|library_name|corner|effort)\}", arg):
        raise ProfileError(f"Unresolved placeholder in step argument: {arg}")
    return arg


def execute_steps(profile, request, root):
    condition = request["condition"]
    sources = sorted(p for p in Path(request["sources"]).rglob("*") if p.is_file())
    filelist = root / "filelist.f"
    filelist.write_text("".join(f"{p}\n" for p in sources))
    params = root / "parameters.json"
    params.write_text(json.dumps(condition["task"].get("parameters", {}), sort_keys=True))
    values = {"{sources}": request["sources"], "{filelist}": filelist, "{top}": condition["task"]["top"], "{work}": root,
              "{params_json}": params, "{clock_period_ns}": condition["workload"]["clock_period_ns"],
              "{workload_id}": condition["workload"]["id"], "{library_name}": condition["library"]["name"],
              "{corner}": condition["library"]["corner"], "{effort}": condition["effort"]}
    values.update({"{asset:" + k + "}": v for k, v in request["assets"].items()})
    logs = []
    for index, step in enumerate(profile["steps"]):
        log = root / f"step-{index}-{step['role']}.log"
        logs.append(log.name)
        argv = [substitute(a, values) for a in step["argv"]]
        with log.open("wb") as stream:
            try:
                proc = subprocess.run(argv, cwd=root, env=os.environ.copy(), stdout=stream, stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL, timeout=step.get("timeout_seconds"))
            except subprocess.TimeoutExpired:
                return logs, f"step {step['role']} exceeded its timeout"
            except OSError as exc:
                return logs, f"step {step['role']} could not start: {exc}"
        if proc.returncode != 0:
            return logs, f"step {step['role']} exited with {proc.returncode}"
    return logs, None


def main(profile_path, request_path, response_path):
    request = json.loads(Path(request_path).read_text())
    response = Path(response_path)
    root = response.parent
    root.mkdir(parents=True, exist_ok=True)
    condition = request["condition"]
    value = {k: request[k] for k in ("job_id", "input_fingerprint", "condition_fingerprint", "source_hashes")}
    value.update(schema_version=1, mode=condition["mode"], stage=condition["stage"], license_wait_seconds=None)
    trace = root / "wrapper-trace.txt"
    files = [trace.name]
    reason = None
    profile = None
    try:
        profile = load_profile(profile_path)
        logs, reason = execute_steps(profile, request, root)
        files += logs
    except (ProfileError, OSError, KeyError, ValueError) as exc:
        reason = f"profile or step configuration error: {exc}"
    if reason is None:
        try:
            metrics = parse_metrics(profile, root)
            quality = parse_quality(profile, root)
            activity = profile["activity"]["report"]
            if not safe_report(root, activity).is_file() or safe_report(root, activity).stat().st_size == 0:
                raise ProfileError(f"Candidate activity report missing or empty: {activity}")
            wait = extract(profile["license_wait"], root, "license_wait") if profile.get("license_wait") else None
            files += report_names(profile)
            value.update(status="ok", reason="Parsed by site profile", metrics=metrics, units=METRICS, quality=quality,
                         license_wait_seconds=wait,
                         activity={"source_fingerprint": sha(canonical(request["source_hashes"])),
                                   "workload_fingerprint": sha(canonical(condition["workload"])), "report": activity})
        except (ProfileError, OSError, KeyError, TypeError, re.error) as exc:
            reason = f"report parsing failed: {exc}"
    if reason is not None:
        value.update(status="infra_error", reason=reason)
    trace.write_text(f"status={value['status']}\nreason={value['reason']}\n")
    existing = [name for name in dict.fromkeys(files) if safe_report(root, name).is_file()]
    value["reports"] = {name: sha(safe_report(root, name).read_bytes()) for name in existing}
    response.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: eda_profile_wrapper.py PROFILE REQUEST RESPONSE")
    main(*sys.argv[1:])
