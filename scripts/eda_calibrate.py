#!/usr/bin/env python3
"""Calibrate a site EDA profile against real reports, without running any EDA tool.

  versions:  run the profile's version commands and record what the installed tools report.
  reports:   parse existing raw reports and compare with values a person read from those reports.

A calibration record ties the profile hash and report hashes to the comparison. Changing the
profile invalidates the record, so calibrate again after a tool or report-format change.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eda_profile_wrapper import METRICS, PLACEHOLDER, ProfileError, load_profile, parse_metrics, parse_quality, report_names, safe_report  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def refuse_existing(path):
    if Path(path).exists():
        raise SystemExit(f"Refusing to overwrite calibration evidence: {path}")


def probe(args):
    """Version commands are allowed before the rest of the profile is finished."""
    refuse_existing(args.out)
    raw = json.loads(Path(args.profile).read_text())
    tools = raw.get("version_probes")
    if not isinstance(tools, list) or not tools:
        raise SystemExit("Profile has no version_probes list")
    rows = []
    for tool in tools:
        row = {"role": tool.get("role"), "name": tool.get("name"), "argv": tool.get("argv")}
        if PLACEHOLDER in json.dumps(tool):
            rows.append(row | {"status": "not_configured", "version": None})
            continue
        try:
            done = subprocess.run(tool["argv"], capture_output=True, text=True, errors="replace",
                                  stdin=subprocess.DEVNULL, timeout=tool.get("timeout_seconds", 60))
            output = done.stdout + done.stderr
            match = re.search(tool["regex"], output, flags=re.M)
            if done.returncode != 0 or not match:
                rows.append(row | {"status": "unrecognized", "version": None, "exit": done.returncode, "output": output[:600]})
            else:
                rows.append(row | {"status": "ok", "version": match[1], "exit": done.returncode})
        except (OSError, subprocess.TimeoutExpired, KeyError, re.error, IndexError) as exc:
            rows.append(row | {"status": "error", "version": None, "error": str(exc)})
    Path(args.out).write_text(json.dumps({"schema_version": 1, "profile_sha256": sha(args.profile), "tools": rows},
                                         indent=2, ensure_ascii=False) + "\n")
    for row in rows:
        print(f"{row['role']}: {row['status']} {row['version']}")
    return 0 if all(r["status"] == "ok" for r in rows) else 1


def compare(args):
    refuse_existing(args.out)
    expected = json.loads(Path(args.expected).read_text())
    missing = set(METRICS) - set(expected.get("metrics", {}))
    if missing:
        raise SystemExit(f"Expected values must cover {sorted(METRICS)}; missing {sorted(missing)}")
    for name in METRICS:
        value = expected["metrics"][name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise SystemExit(f"Expected {name} must be a finite nonnegative number in {METRICS[name]}: {value!r}")
    if not isinstance(expected.get("read_by"), str) or not expected["read_by"].strip():
        raise SystemExit("Expected file requires read_by: who read the values from the raw reports")
    profile = load_profile(args.profile)
    root = Path(args.reports).resolve()
    record = {"schema_version": 1, "kind": "eda_calibration", "profile_sha256": sha(args.profile),
              "tolerance_pct": args.tolerance_pct, "read_by": expected["read_by"],
              "reference_design": expected.get("reference_design"), "units": METRICS,
              "scope": "Parser and unit check on one report set. Not proof that tool settings or PPA values are appropriate."}
    try:
        parsed = parse_metrics(profile, root)
        quality = parse_quality(profile, root)
        record["reports"] = {name: sha(safe_report(root, name)) for name in report_names(profile) if safe_report(root, name).is_file()}
    except (ProfileError, OSError, KeyError, re.error) as exc:
        record.update(status="parse_failed", reason=str(exc))
        Path(args.out).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        print(f"parse_failed: {exc}")
        return 1
    rows = {}
    for name in METRICS:
        want = float(expected["metrics"][name])
        delta = abs(parsed[name] - want) / want * 100 if want else (0.0 if parsed[name] == 0 else float("inf"))
        rows[name] = {"parsed": parsed[name], "expected": want, "delta_pct": delta if delta != float("inf") else None,
                      "within_tolerance": delta <= args.tolerance_pct}
    quality_ok = all(quality[k] == v for k, v in expected.get("quality", {}).items())
    status = "calibrated" if all(r["within_tolerance"] for r in rows.values()) and quality_ok else "mismatch"
    record.update(status=status, metrics=rows, quality=quality, expected_quality=expected.get("quality", {}))
    Path(args.out).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    for name, row in rows.items():
        print(f"{name}: parsed={row['parsed']} expected={row['expected']} within={row['within_tolerance']}")
    print(status)
    return 0 if status == "calibrated" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("versions")
    p.add_argument("--profile", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=probe)
    p = sub.add_parser("reports")
    p.add_argument("--profile", required=True)
    p.add_argument("--reports", required=True)
    p.add_argument("--expected", required=True)
    p.add_argument("--tolerance-pct", type=float, default=0.5)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=compare)
    args = parser.parse_args()
    try:
        return args.fn(args)
    except ProfileError as exc:
        print(f"profile error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
