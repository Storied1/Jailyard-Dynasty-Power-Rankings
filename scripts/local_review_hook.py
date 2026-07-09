#!/usr/bin/env python
"""
Post-Edit Review Hook — sends git diffs to local Qwen 3 8B for a fast
second-opinion code review after Claude Code edits files.

Called as a Claude Code hook (PostToolUse on Write/Edit). Reads the current
unstaged diff and asks the local model if anything looks off.

Usage (standalone test):
    python scripts/local_review_hook.py

As a hook, this is registered in .claude/settings.json and runs automatically.
Exit code 0 = pass (review printed to stderr as info).
"""

import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Ensure shared.py is importable when run as a hook from any CWD
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared import MODEL_LIGHT as REVIEW_MODEL
from shared import OLLAMA_BASE

HOOK_FAILURE_LOG = Path.home() / ".claude" / "hook-failures.log"


def _log_failure(context, exc):
    """Best-effort append to ~/.claude/hook-failures.log — never raise."""
    try:
        ts = datetime.now(timezone.utc).isoformat()
        with open(HOOK_FAILURE_LOG, "a", encoding="utf-8") as f:
            f.write(f"{ts} local_review_hook.py {context}: {exc!r}\n")
    except Exception:
        pass


def get_diff():
    """Get the current unstaged git diff."""
    try:
        result = subprocess.run(
            ["git", "diff", "--no-color", "--unified=3"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()
    except Exception as e:
        _log_failure("get_diff", e)
        return ""


def review_diff(diff):
    """Send diff to local model for review."""
    if not diff or len(diff) < 20:
        return None

    # Truncate very large diffs
    if len(diff) > 4000:
        diff = diff[:4000] + "\n... (truncated)"

    payload = {
        "model": REVIEW_MODEL,
        "prompt": (
            "You are a code reviewer. Review this git diff briefly. "
            "Only flag actual problems — bugs, security issues, broken logic. "
            "If everything looks fine, say 'LGTM'. Be concise (1-3 lines max). "
            "/no_think\n\n"
            f"```diff\n{diff}\n```"
        ),
        "stream": False,
        # /no_think disables thinking mode — no need to double num_predict
        "options": {"temperature": 0.2, "num_predict": 512},
    }

    url = f"{OLLAMA_BASE}/api/generate"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            text = result.get("response", "").strip()
            # Qwen 3 thinking mode: if response is empty, content was consumed
            # by thinking. That's fine — means the model had nothing to flag.
            return text if text else None
    except Exception as e:
        _log_failure("review_diff", e)
        return None  # advisory only — Ollama being down shouldn't block the hook


def main():
    """Hook entry point — reads hook input from stdin, reviews diff."""
    # Read hook input (JSON from Claude Code)
    hook_input = {}
    try:
        raw = sys.stdin.read()
        if raw.strip():
            hook_input = json.loads(raw)
    except Exception as e:
        _log_failure("main:stdin_parse", e)

    # Only run on Write/Edit tool completions
    tool_name = hook_input.get("tool_name", "")
    if tool_name and tool_name not in ("Write", "Edit"):
        sys.exit(0)

    diff = get_diff()
    if not diff:
        sys.exit(0)

    review = review_diff(diff)
    if review and "LGTM" not in review.upper():
        # Print review as info (goes to Claude Code output)
        print(f"[Local Review] {review}", file=sys.stderr)

    # Always exit 0 — this is advisory, not blocking
    sys.exit(0)


if __name__ == "__main__":
    main()
