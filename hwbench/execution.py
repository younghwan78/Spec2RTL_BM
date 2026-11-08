import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request

from .common import canonical, digest, execute, portable_logs, sandbox_available, task_base, within, write_json
from .grader import grade_task, new_result, task_plan


def export_task(suite, task, dest):
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise ValueError(f"Export destination must be empty: {dest}")
    dest.mkdir(parents=True, exist_ok=True)
    base = task_base(suite, task)
    prompt = (base / "prompt.md").read_text()
    prompt += "\n\nAllowed submission files:\n" + "\n".join(f"- {f}" for f in task["files"])
    prompt += "\nModify only these RTL files. Do not modify tests or grading configuration.\n"
    (dest / "prompt.md").write_text(prompt)
    for name in task["files"]:
        dst = within(dest, name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(within(base / "starter", name), dst)
    write_json(dest / "task.json", {"id": task["id"], "files": task["files"],
                                   "suite_fingerprint": suite["fingerprint"]})


def export_suite(suite, dest):
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise ValueError("Export root must be empty")
    for t in suite["tasks"]:
        export_task(suite, t, dest / t["id"])
    write_json(dest / "manifest.json", {"suite_id": suite["id"], "fingerprint": suite["fingerprint"],
                                       "tasks": [{"id": t["id"], "files": t["files"]} for t in suite["tasks"]]})


def parse_files(text, allowed):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    obj = json.loads(text)
    if not isinstance(obj, dict) or set(obj) != {"files"} or not isinstance(obj["files"], dict):
        raise ValueError('Model must return {"files": {"rtl/name.sv": "source"}}')
    if set(obj["files"]) != set(allowed) or not all(isinstance(v, str) for v in obj["files"].values()):
        raise ValueError("Returned files must exactly match allowed submission files")
    return obj["files"]


def _http_request(config, workspace, task, timeout, logdir):
    endpoint = config["base_url"].rstrip("/") + "/chat/completions"
    if not endpoint.startswith(("http://", "https://")):
        raise ValueError("base_url must use http(s)")
    prompt = (workspace / "prompt.md").read_text()
    context = {f: (workspace / f).read_text() for f in task["files"]}
    payload = {"model": config["model"], "messages": [
        {"role": "system", "content": 'Implement synthesizable RTL. Return only JSON {"files": {"path": "complete source"}} for every allowed file.'},
        {"role": "user", "content": prompt + "\n\nStarter files:\n" + json.dumps(context)}]}
    for key in ("temperature", "max_tokens", "seed"):
        if key in config:
            payload[key] = config[key]
    headers = {"Content-Type": "application/json"}
    if config.get("api_key_env"):
        key = os.environ.get(config["api_key_env"])
        if not key:
            raise RuntimeError(f"Missing API key environment variable: {config['api_key_env']}")
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers=headers)
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(4_000_001)
        if len(raw) > 4_000_000:
            raise ValueError("API response exceeded size limit")
        body = json.loads(raw)
        text = body["choices"][0]["message"]["content"]
    except TimeoutError:
        return {"status": "timeout", "reason": "API request exceeded time budget", "seconds": time.monotonic() - start}
    except (urllib.error.URLError, OSError) as exc:
        # Do not include a URL or response body that could contain credentials.
        return {"status": "infra_error", "reason": type(exc).__name__, "seconds": time.monotonic() - start}
    except (ValueError, KeyError, IndexError, TypeError):
        return {"status": "invalid_submission", "reason": "Invalid API response schema", "seconds": time.monotonic() - start}
    logdir.mkdir(parents=True, exist_ok=True)
    (logdir / "completion.txt").write_text(text if isinstance(text, str) else repr(text))
    try:
        files = parse_files(text, task["files"])
        for name, content in files.items():
            within(workspace, name).write_text(content)
    except (ValueError, AttributeError, TypeError) as exc:
        return {"status": "invalid_submission", "reason": str(exc), "seconds": time.monotonic() - start,
                "usage": body.get("usage", {})}
    return {"status": "ok", "seconds": round(time.monotonic() - start, 6), "usage": body.get("usage", {}),
            "log": str((logdir / "completion.txt").resolve())}


def openai_completion(config, workspace, task, timeout, logdir):
    """Supervised subprocess enforces total wallclock, including slow HTTP streams."""
    from .common import ROOT
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("API timeout must be finite and positive")
    logdir = Path(logdir).resolve();logdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hwbench-http-") as tmp:
        request_file = Path(tmp) / "request.json"
        response_file = Path(tmp) / "response.json"
        write_json(request_file, {"config": config, "workspace": str(Path(workspace).resolve()),
                                 "task": task, "timeout": timeout, "logdir": str(logdir)})
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        process = execute([sys.executable, "-m", "hwbench.http_worker", str(request_file), str(response_file)],
                          ROOT, logdir / "http-worker.log", timeout, env)
        if process["timeout"]:
            return {"status": "timeout", "reason": "API total wall-clock budget exceeded",
                    "seconds": process["seconds"], "log": process["log"]}
        if process.get("error") or process["returncode"] != 0 or not response_file.is_file():
            return {"status": "infra_error", "reason": "HTTP worker failed", "seconds": process["seconds"], "log": process["log"]}
        result = json.loads(response_file.read_text())
        result["seconds"] = process["seconds"]
        return result


def run(suite, config, out, repeats=1, seeds=None, check_timeout=10, agent_timeout=300, sandbox="auto"):
    if repeats < 1 or not math.isfinite(agent_timeout) or agent_timeout <= 0 or not math.isfinite(check_timeout) or check_timeout <= 0:
        raise ValueError("Repeats and timeouts must be positive")
    if config.get("type") not in ("command", "openai"):
        raise ValueError("Adapter type must be command or openai")
    if config["type"] == "command":
        argv = config.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            raise ValueError("Command adapter requires a nonempty argv list; shell strings are not accepted")
    out = Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"Run output must be empty: {out}")
    seeds = seeds or [1, 7, 42]
    isolated = sandbox_available() if sandbox != "off" else False
    if sandbox == "required" and not isolated:
        raise ValueError("Required bubblewrap unavailable")
    metadata = {k: config[k] for k in ("model", "model_revision", "quantization", "harness", "harness_version",
                                     "temperature", "max_tokens", "seed", "notes") if k in config}
    metadata["adapter_type"] = config["type"]
    metadata["agent_isolation"] = "external responsibility; runner command executes on host"
    metadata["adapter_config_sha256"] = digest(canonical(config))
    kind = config.get("kind", "model_run")
    if kind not in ("model_run", "fixture_adapter"):
        raise ValueError("Configured kind must be model_run or fixture_adapter")
    result = new_result(suite, config.get("label", config.get("model", "unnamed")), kind, seeds,
                        check_timeout, isolated, metadata)
    result["protocol"].update(execution_mode=config["type"], agent_timeout_seconds=agent_timeout,
                              generation_settings={k: config.get(k, "unspecified") for k in ("temperature", "max_tokens", "seed")})
    result["protocol_fingerprint"] = digest(canonical(result["protocol"]))
    result.update(planned_runs=len(suite["tasks"]) * repeats, task_count=len(suite["tasks"]), repeats=repeats)
    result["task_plan"] = task_plan(suite, repeats)
    write_json(out / "results.json", result)
    for repeat in range(1, repeats + 1):
        for task in suite["tasks"]:
            key = f"{task['id']}-r{repeat}"
            work = out / "workspaces" / key
            export_task(suite, task, work)
            logs = out / "tasks" / key
            logs.mkdir(parents=True, exist_ok=True)
            if config["type"] == "command":
                replacements = {"{workspace}": str(work), "{prompt}": str(work / "prompt.md"),
                                "{task_id}": task["id"]}
                argv = config["argv"][:]
                for i, arg in enumerate(argv):
                    for token, value in replacements.items():
                        arg = arg.replace(token, value)
                    argv[i] = arg
                if any(str(x) in arg for x in ("{workspace}", "{prompt}", "{task_id}") for arg in argv):
                    raise ValueError("Unexpanded command placeholder")
                agent = execute(argv, work, logs / "agent.log", agent_timeout)
                if agent.get("error"):
                    agent.update(status="infra_error", reason=agent["error"])
                elif agent["timeout"]:
                    agent.update(status="timeout", reason="Agent exceeded wall-clock budget")
                elif agent["returncode"] != 0 or agent["output_limit"]:
                    agent.update(status="agent_error", reason="Agent command failed or exceeded output limit")
                else:
                    agent["status"] = "ok"
            else:
                try:
                    agent = openai_completion(config, work, task, agent_timeout, logs)
                except (ValueError, RuntimeError) as exc:
                    agent = {"status": "infra_error", "reason": str(exc), "seconds": 0}
            if agent["status"] == "ok":
                row = grade_task(suite, task, work, logs, seeds, check_timeout, isolated)
            else:
                row = {"task_id": task["id"], "title": task["title"], "category": task["category"],
                       "difficulty": task.get("difficulty", "unknown"), "backend": "native",
                       "tier": task.get("tier", "unknown"), "domain": task.get("domain", "unknown"),
                       "failure_phase": "agent", "status": agent["status"], "reason": agent.get("reason", ""), "checks": [],
                       "source_hashes": {}, "required_checks": len(task["checks"]) * len(seeds), "seconds": None}
            row.update(repeat=repeat, agent=agent)
            portable_logs(row, out)
            result["tasks"].append(row)
            write_json(out / "results.json", result)
    return result
