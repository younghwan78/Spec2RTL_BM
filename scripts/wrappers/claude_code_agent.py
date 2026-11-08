#!/usr/bin/env python3
"""Run Claude Code headlessly on one exported HWBench task.

Usage (from a command adapter config): claude_code_agent.py WORKSPACE PROMPT_FILE

Environment:
  HWB_CC_MODEL      required; model alias or full name, recorded in the run config as well
  HWB_CC_TOOLS      built-in tools, default "Read,Edit,Write,Glob,Grep" (no shell)
  HWB_CC_MODE       permission mode, default "acceptEdits"
  HWB_CC_MAX_TURNS  optional turn limit
  HWB_CC_BIN        optional path to the claude executable

Connection variables such as ANTHROPIC_BASE_URL pass through unchanged. This wrapper does not
isolate the agent. Run it where only export output is visible. Results depend on the installed
Claude Code version, so record that version in the run config.
"""
import os
from pathlib import Path
import subprocess
import sys


def build_command(env):
    model = env.get("HWB_CC_MODEL", "").strip()
    if not model:
        raise SystemExit("HWB_CC_MODEL must name the evaluated model")
    argv = [env.get("HWB_CC_BIN", "claude"), "-p", "--output-format", "json", "--model", model,
            "--tools", env.get("HWB_CC_TOOLS", "Read,Edit,Write,Glob,Grep"),
            "--permission-mode", env.get("HWB_CC_MODE", "acceptEdits"),
            "--setting-sources", "project", "--strict-mcp-config", "--disable-slash-commands",
            "--no-session-persistence"]
    if env.get("HWB_CC_MAX_TURNS"):
        argv += ["--max-turns", env["HWB_CC_MAX_TURNS"]]
    return argv


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: claude_code_agent.py WORKSPACE PROMPT_FILE")
    workspace, prompt = Path(sys.argv[1]), Path(sys.argv[2])
    env = os.environ.copy()
    # Instructions and notes from the host account would change the evaluated condition.
    env.update(CLAUDE_CODE_DISABLE_CLAUDE_MDS="1", CLAUDE_CODE_DISABLE_AUTO_MEMORY="1",
               CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1", DISABLE_TELEMETRY="1", DISABLE_ERROR_REPORTING="1")
    with prompt.open("rb") as stream:
        return subprocess.run(build_command(env), cwd=workspace, env=env, stdin=stream).returncode


if __name__ == "__main__":
    sys.exit(main())
