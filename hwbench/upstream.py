"""Import official HWE results; never reinterpret Harbor's stub reward."""
import datetime
import json
from pathlib import Path
import uuid

from .common import canonical, digest, write_json


def import_hwe(path, out, label, dataset_id, expected_ids=None):
    raw = Path(path).read_bytes()
    obj = json.loads(raw)
    groups = {"resolved_ids": "pass", "unresolved_ids": "fail",
              "empty_patch_ids": "empty_patch", "error_ids": "infra_error"}
    seen = set()
    tasks = []
    for key, status in groups.items():
        values = obj.get(key)
        if not isinstance(values, list):
            raise ValueError(f"Missing official HWE final_report list: {key}")
        for tid in values:
            if not isinstance(tid, str) or not tid or tid in seen:
                raise ValueError(f"Invalid or overlapping HWE ID: {tid!r}")
            seen.add(tid)
            tasks.append({"task_id": tid, "title": tid, "category": "repository", "repeat": 1,
                          "status": status, "reason": key, "checks": [], "seconds": None})
    if not seen:
        raise ValueError("Empty HWE report")
    if expected_ids is not None and set(expected_ids) != seen:
        raise ValueError("HWE report does not match expected task IDs")
    protocol = {"upstream": "hwe-bench", "dataset_id": dataset_id, "task_ids": sorted(seen),
                "evaluator_protocol": "unverified external import"}
    result = {"schema_version": 1, "run_id": uuid.uuid4().hex[:12], "label": label,
              "kind": "upstream_import", "origin": "hwe_official_report_import",
              "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "suite_id": dataset_id, "suite_fingerprint": digest(canonical(protocol)),
              "protocol": protocol, "protocol_fingerprint": digest(canonical(protocol)),
              "task_count": len(tasks), "planned_runs": len(tasks), "repeats": 1,
              "tools": {}, "metadata": {"source_sha256": digest(raw), "execution_verified_here": False,
                                         "expected_task_set_verified": expected_ids is not None},
              "tasks": tasks, "file_hashes": {},
              "limitations": ["Imported official final_report; evaluator was not executed or authenticated here.",
                              "Per-check logs, timing, tools and complete regression coverage are not supplied.",
                              "Task membership is not checked against a pinned dataset unless --expected-ids is supplied."]}
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Import output must be empty")
    write_json(out / "upstream_final_report.json", obj)
    write_json(out / "results.json", result)
    return result
