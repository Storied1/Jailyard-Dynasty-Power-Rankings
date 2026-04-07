"""Shared utilities for Jailyard Dynasty scripts.

Consolidates duplicated paths, JSON I/O, Ollama API calls, and constants
that were previously copy-pasted across 17+ scripts.
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths — single source of truth for all project directories
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CONTENT_DIR = REPO_ROOT / "content"
WEEKS_DIR = CONTENT_DIR / "weeks"
CHAT_DIR = REPO_ROOT / "chat"
CONTENT_CHAT_DIR = CONTENT_DIR / "chat"
MAP_CACHE_DIR = CONTENT_CHAT_DIR / ".map_cache"
NAME_MAP_PATH = CONTENT_CHAT_DIR / "name-map.json"
TEAM_PROFILES_PATH = CONTENT_DIR / "team-profiles.json"
VOICE_BIBLE_PATH = CONTENT_DIR / "voice-bible.md"


# ---------------------------------------------------------------------------
# JSON I/O
# ---------------------------------------------------------------------------


def load_json(path, label=None, required=False, warn=None):
    """Load a JSON file.

    Args:
        path: Path to the JSON file.
        label: Optional label for error/warning messages (defaults to filename).
        required: If True, exit with error when file is missing.
        warn: If True and file is missing, print a warning. Defaults to True
              when label is provided, False otherwise.
    """
    path = Path(path)
    if warn is None:
        warn = label is not None
    if not path.exists():
        tag = label or path.name
        if required:
            print(f"ERROR: {tag} not found at {path}")
            sys.exit(1)
        if warn:
            print(f"  WARN: {tag} not found at {path}")
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_ts(ts_str):
    """Parse an ISO-8601 timestamp string to a timezone-aware UTC datetime.

    Returns None for None input or unparseable strings.
    """
    if ts_str is None:
        return None
    s = ts_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def save_json(path, data, indent=2, ensure_ascii=False, verbose=False):
    """Write data to a JSON file with consistent formatting.

    Creates parent directories if needed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
    if verbose:
        print(f"  Saved: {path.relative_to(REPO_ROOT)}")


# ---------------------------------------------------------------------------
# Ollama API
# ---------------------------------------------------------------------------

OLLAMA_BASE = "http://localhost:11434"
MODEL_HEAVY = "qwen3:30b-a3b"
MODEL_LIGHT = "qwen3:8b"
EMBED_MODEL = "nomic-embed-text"


def ollama_request(endpoint, payload, timeout=300):
    """Generic POST to Ollama API. Returns parsed JSON response.

    Args:
        endpoint: API path, e.g. "/api/generate" or "/api/embed".
        payload: Dict to JSON-encode as the request body.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON dict on success, or dict with "error" key on failure.
    """
    url = f"{OLLAMA_BASE}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"error": f"Ollama unreachable at {OLLAMA_BASE}: {e}"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Constants — magic numbers extracted from various scripts
# ---------------------------------------------------------------------------

# Embedding
EMBEDDING_BATCH_SIZE = 50

# Chat timing thresholds (seconds)
CONVERSATION_GAP_SEC = 1800  # 30 min — new conversation block
REPLY_WINDOW_SEC = 120  # 2 min — counts as a reply
RAPID_BURST_SEC = 300  # 5 min — rapid burst window

# Fingerprint analysis
UPPERCASE_THRESHOLD = 0.5
DISTINCTIVE_WORD_RATIO = 3.0
VOWEL_RATIO_MIN = 0.30
DISTINCTIVE_WORD_MIN_COUNT = 8
DISTINCTIVE_WORDS_KEEP = 20

# Consensus detection
CONSENSUS_WINDOW_SIZE = 20
CONSENSUS_MIN_SENDERS = 4

# Media processing
MAX_IMAGE_SIZE = 1024
JPEG_QUALITY = 85
DESCRIPTION_BATCH_SIZE = 5
GIPHY_CANDIDATES_PER_SLOT = 3

# Token budgets (LLM generation) — used by local_draft.py, batch_drafts.py
SECTION_TOKEN_BUDGETS = {
    "essay": 4096,
    "rankings": 6144,
    "confessionals": 2048,
    "mailbag": 2048,
    "bits": 1024,
}
