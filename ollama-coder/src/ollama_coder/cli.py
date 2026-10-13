"""Interactive, approval-based coding assistant for local Ollama models."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "qwen3:8b"
MAX_FILE_BYTES = 1_000_000
MAX_RESULT_CHARS = 16_000
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}
SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}
SENSITIVE_NAMES = {"credentials", "secrets", "id_rsa", "id_ed25519"}

SYSTEM_PROMPT = """You are a coding assistant working in the user's current project.
Inspect relevant files before proposing changes. Use the provided tools for project
context and implementation. Explain your plan briefly before making changes, and
ask for approval before every file write or shell command (the tools enforce this).
Do not read or expose credentials, tokens, private keys, or secret files. Do not
delete files, run destructive commands, or use git reset/clean/stash/force-push.
Run focused tests or checks after editing and report their actual results.

Only create a branch, commit, or push when the user explicitly asks. Before doing
so, inventory the current branch's changes and show the user the changed files.
Ask for a branch name before creating one and an exact commit message before
committing, unless the user already supplied them. Resolve an unambiguous GitHub
remote, check authentication without revealing credentials, and push only the
newly created branch. Never claim an operation succeeded unless it did."""

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List project files under a relative directory. Secret files are omitted.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Relative directory, default '.'"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 project text file. Secret files and large files are blocked.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "File path relative to the project"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_text",
            "description": "Search project text files for a literal string, omitting secret files.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "path": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or replace a project file after showing a diff and obtaining user approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to the project"},
                    "content": {"type": "string", "description": "Complete UTF-8 file contents"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command in the project directory after showing it and obtaining user approval.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]


class CoderError(Exception):
    """An actionable error shown to the CLI user."""


def _is_sensitive(path: Path) -> bool:
    name = path.name.lower()
    return (
        name in SENSITIVE_NAMES
        or name == ".env"
        or name.startswith(".env.")
        or path.suffix.lower() in SENSITIVE_SUFFIXES
    )


def _project_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise CoderError("Use a path relative to the project directory.")
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise CoderError("That path resolves outside the project directory.") from exc
    if ".git" in (part.lower() for part in target.relative_to(root).parts):
        raise CoderError("Access to the .git directory is blocked.")
    if _is_sensitive(target):
        raise CoderError("Access to files that may contain secrets is blocked.")
    return target


def _approved(action: str) -> bool:
    try:
        answer = input(f"{action}\nApprove? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def _project_files(root: Path, start: Path):
    for directory, subdirs, filenames in os.walk(start):
        subdirs[:] = sorted(d for d in subdirs if d not in SKIP_DIRS)
        for filename in sorted(filenames):
            path = Path(directory) / filename
            if not _is_sensitive(path):
                yield path


def _list_files(root: Path, args: dict[str, Any]) -> str:
    start = _project_path(root, str(args.get("path", ".")))
    if not start.is_dir():
        raise CoderError(f"Not a directory: {args.get('path', '.')}")
    results = []
    for path in _project_files(root, start):
        results.append(path.relative_to(root).as_posix())
        if len(results) == 300:
            results.append("... truncated after 300 files")
            break
    return "\n".join(results) if results else "No project files found."


def _read_file(root: Path, args: dict[str, Any]) -> str:
    path = _project_path(root, str(args.get("path", "")))
    if not path.is_file():
        raise CoderError(f"File not found: {args.get('path', '')}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise CoderError("File exceeds the 1 MB read limit.")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise CoderError("This file is not UTF-8 text and cannot be read by this tool.") from exc


def _search_text(root: Path, args: dict[str, Any]) -> str:
    query = str(args.get("query", ""))
    if not query:
        raise CoderError("Search query cannot be empty.")
    start = _project_path(root, str(args.get("path", ".")))
    if not start.is_dir():
        raise CoderError(f"Not a directory: {args.get('path', '.')}")
    matches = []
    for path in _project_files(root, start):
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(lines, start=1):
            if query.casefold() in line.casefold():
                matches.append(f"{path.relative_to(root).as_posix()}:{line_number}: {line[:500]}")
                if len(matches) == 100:
                    matches.append("... truncated after 100 matches")
                    return "\n".join(matches)
    return "\n".join(matches) if matches else "No matches found."


def _write_file(root: Path, args: dict[str, Any]) -> str:
    path = _project_path(root, str(args.get("path", "")))
    if not path.parent.is_dir():
        raise CoderError("The parent directory must already exist.")
    content = args.get("content")
    if not isinstance(content, str):
        raise CoderError("File content must be text.")
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise CoderError("File exceeds the 1 MB write limit.")
    if path.exists() and not path.is_file():
        raise CoderError("The target exists and is not a regular file.")
    try:
        old_content = path.read_text(encoding="utf-8") if path.exists() else ""
    except UnicodeDecodeError as exc:
        raise CoderError("Refusing to replace a non-UTF-8 file.") from exc

    diff = list(
        difflib.unified_diff(
            old_content.splitlines(),
            content.splitlines(),
            fromfile=f"a/{path.relative_to(root).as_posix()}",
            tofile=f"b/{path.relative_to(root).as_posix()}",
            lineterm="",
        )
    )
    preview = "\n".join(diff[:100])
    if len(diff) > 100:
        preview += "\n... diff truncated after 100 lines"
    if not diff:
        return "File is unchanged; no write was made."
    if not _approved(f"Proposed file change:\n{preview}"):
        return "User declined the file change; nothing was written."
    path.write_text(content, encoding="utf-8", newline="")
    return f"Wrote {path.relative_to(root).as_posix()} ({len(content)} characters)."


def _run_command(root: Path, args: dict[str, Any]) -> str:
    command = str(args.get("command", "")).strip()
    if not command:
        raise CoderError("Command cannot be empty.")
    if not _approved(f"Command (working directory: {root}):\n{command}"):
        return "User declined the command; it was not run."
    try:
        result = subprocess.run(
            command,
            cwd=root,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CoderError("Command timed out after 120 seconds.") from exc
    except OSError as exc:
        raise CoderError(f"Could not start command: {exc}") from exc
    output = (result.stdout + result.stderr).strip()
    if not output:
        output = "(no output)"
    if len(output) > MAX_RESULT_CHARS:
        output = output[:MAX_RESULT_CHARS] + "\n... output truncated"
    return f"Exit code: {result.returncode}\n{output}"


def _call_tool(root: Path, name: str, args: dict[str, Any]) -> str:
    tools = {
        "list_files": _list_files,
        "read_file": _read_file,
        "search_text": _search_text,
        "write_file": _write_file,
        "run_command": _run_command,
    }
    handler = tools.get(name)
    if handler is None:
        return f"Tool error: unsupported tool {name!r}."
    try:
        return handler(root, args)
    except (CoderError, OSError) as exc:
        return f"Tool error: {exc}"


def _request_json(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise CoderError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CoderError(
            f"Cannot reach Ollama at {url}. Start Ollama and check the --host value. Details: {exc}"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoderError("Ollama returned an invalid JSON response.") from exc
    if not isinstance(decoded, dict):
        raise CoderError("Ollama returned an unexpected response.")
    return decoded


def _check_model(host: str, model: str) -> None:
    tags = _request_json(f"{host}/api/tags")
    installed = {entry.get("name") for entry in tags.get("models", []) if isinstance(entry, dict)}
    if model not in installed:
        raise CoderError(
            f"Model {model!r} is not installed. Run `ollama pull {model}` or choose an installed "
            "model with --model. Installed models: " + (", ".join(sorted(installed)) or "(none)")
        )


def _chat_turn(host: str, model: str, messages: list[dict[str, Any]], root: Path) -> str:
    for _ in range(10):
        response = _request_json(
            f"{host}/api/chat",
            {"model": model, "messages": messages, "tools": TOOL_DEFINITIONS, "stream": False},
        )
        message = response.get("message")
        if not isinstance(message, dict):
            raise CoderError("Ollama chat response did not contain a message.")
        messages.append(message)
        tool_calls = message.get("tool_calls", [])
        if not tool_calls:
            return str(message.get("content", "")).strip()
        for call in tool_calls:
            function = call.get("function", {}) if isinstance(call, dict) else {}
            name = function.get("name")
            args = function.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            if not isinstance(name, str) or not isinstance(args, dict):
                result = "Tool error: invalid tool call format."
                name = str(name or "unknown")
            else:
                result = _call_tool(root, name, args)
            messages.append({"role": "tool", "tool_name": name, "content": result})
    raise CoderError("Stopped after 10 tool rounds to avoid an unbounded model loop.")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ollama-coder",
        description="Code in the current project using a local Ollama model.",
    )
    parser.add_argument("prompt", nargs="*", help="Task to do (omit to start interactive chat)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--host", default="http://localhost:11434", help="Ollama URL")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="Project directory")
    args = parser.parse_args()

    root = args.workspace.resolve()
    if not root.is_dir():
        print(f"Error: project directory does not exist: {root}", file=sys.stderr)
        return 2
    host = args.host.rstrip("/")
    try:
        _check_model(host, args.model)
        print(f"Ollama Coder | model: {args.model} | project: {root}")
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        prompts = [" ".join(args.prompt)] if args.prompt else None
        while True:
            try:
                prompt = prompts.pop(0) if prompts is not None else input("\nYou> ").strip()
            except EOFError:
                break
            if not prompt:
                if prompts is not None:
                    break
                continue
            if prompt.lower() in {"/exit", "/quit", "exit", "quit"}:
                break
            messages.append({"role": "user", "content": prompt})
            answer = _chat_turn(host, args.model, messages, root)
            if answer:
                print(f"\nCoder> {answer}")
            if prompts is not None:
                break
        return 0
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    except CoderError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
