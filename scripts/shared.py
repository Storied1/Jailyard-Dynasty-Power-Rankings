"""Shared utilities for Jailyard Dynasty scripts.

Consolidates duplicated paths, JSON I/O, Ollama API calls, and constants
that were previously copy-pasted across 17+ scripts.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths — single source of truth for all project directories
# ---------------------------------------------------------------------------
#
# Root contract (2d — determinism & provenance):
#   SOURCE_ROOT — read-only TRUE sources: chat/_chat.txt, content/chat/name-map.json,
#                 committed content/weeks/week{N}_data.json, and code. Never relocated.
#   OUTPUT_ROOT — owns every DERIVED / generated node: parsed_messages.json,
#                 identity_chain.json, fingerprints.json, .map_cache chunks + MAP
#                 outputs, the analytics files, personas, the 19 chat contexts,
#                 and provenance.json.
# OUTPUT_ROOT defaults to REPO_ROOT, so production paths are byte-identical to
# before. `generate_chat_provenance.py --rebuild-check` sets JAILYARD_OUTPUT_ROOT
# to an external temp tree so the whole DAG rebuilds there without touching the
# canonical repo; every DAG stage READS its intermediate inputs from OUTPUT_ROOT
# (never the canonical copy), keeping a rebuild self-contained.

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPO_ROOT
OUTPUT_ROOT = Path(os.environ.get("JAILYARD_OUTPUT_ROOT") or REPO_ROOT).resolve()

DATA_DIR = REPO_ROOT / "data"
CONTENT_DIR = REPO_ROOT / "content"

# Source dirs / files (read-only; anchored to SOURCE_ROOT)
CHAT_DIR = SOURCE_ROOT / "chat"  # holds _chat.txt (private source)
CHAT_TXT_PATH = CHAT_DIR / "_chat.txt"
CONTENT_CHAT_DIR = CONTENT_DIR / "chat"  # holds name-map.json (source)
NAME_MAP_PATH = CONTENT_CHAT_DIR / "name-map.json"
WEEKS_DIR = CONTENT_DIR / "weeks"  # week{N}_data.json (committed source)
PRESEASON_DIR = CONTENT_DIR / "preseason-2025"
TEAM_PROFILES_PATH = CONTENT_DIR / "team-profiles.json"

# Derived dirs / files (OUTPUT_ROOT-owned; identical to the source dirs when
# OUTPUT_ROOT == REPO_ROOT, i.e. in production).
CHAT_OUT_DIR = OUTPUT_ROOT / "chat"
PARSED_MESSAGES_PATH = CHAT_OUT_DIR / "parsed_messages.json"
IDENTITY_CHAIN_PATH = CHAT_OUT_DIR / "identity_chain.json"
CONTENT_CHAT_OUT_DIR = OUTPUT_ROOT / "content" / "chat"
MAP_CACHE_DIR = CONTENT_CHAT_OUT_DIR / ".map_cache"
WEEKS_OUT_DIR = OUTPUT_ROOT / "content" / "weeks"
PRESEASON_OUT_DIR = OUTPUT_ROOT / "content" / "preseason-2025"


def rel_to_root(path):
    """Root-aware repo-relative POSIX string for log lines.

    Tries OUTPUT_ROOT then SOURCE_ROOT (they coincide in production); falls back
    to the absolute POSIX path for anything under neither (e.g. a temp receipt).
    Replaces bare ``path.relative_to(REPO_ROOT)``, which raises when a stage
    writes under a temp OUTPUT_ROOT during --rebuild-check.
    """
    path = Path(path).resolve()
    for root in (OUTPUT_ROOT, SOURCE_ROOT):
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            continue
    return path.as_posix()


# ---------------------------------------------------------------------------
# Team abbreviation normalization (Phase 1a Task 5 fix-up).
# ff_playerids and some legacy data sources use older abbreviations
# (KCC, GBP, LVR, etc.) while nflreadpy schedules and current Sleeper data use
# modern ones (KC, GB, LV). Sleeper's per-week opponent field also occasionally
# uses legacy abbrevs (LAR, OAK, SDC, STL).
# Normalize ALL team-abbrev usage through normalize_team() to prevent
# comparison drift between data sources.
# ---------------------------------------------------------------------------

FF_TO_SCHED_TEAM = {
    "KCC": "KC",
    "LVR": "LV",
    "GBP": "GB",
    "TBB": "TB",
    "NEP": "NE",
    "NOS": "NO",
    "SFO": "SF",
    "JAC": "JAX",
    "LAR": "LA",
    "OAK": "LV",  # Oakland Raiders -> Las Vegas Raiders (relocated 2020)
    "SDC": "LAC",  # San Diego Chargers -> Los Angeles Chargers (relocated 2017)
    "STL": "LA",  # St. Louis Rams -> Los Angeles Rams (relocated 2016)
    "RAM": "LA",  # alternate Rams abbrev
}


def normalize_team(abbr):
    """Normalize team abbreviation to the modern set used by nflreadpy schedules.

    Applies symmetrically to ALL team-abbrev fields: ff_playerids team,
    Sleeper opponent abbreviations, downstream consumer comparisons.
    Returns None for None input (graceful pass-through).
    """
    if abbr is None:
        return None
    return FF_TO_SCHED_TEAM.get(abbr, abbr)


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


# ---------------------------------------------------------------------------
# Uniform temporal admitter — the exact-cutoff, fail-closed admission boundary
# ---------------------------------------------------------------------------
# The ONE admitter for every writer-facing temporal input across the chat
# pipeline (messages, predictions + nested evidence, jokes, arcs, callbacks).
# Implements the crosswalk Temporal Contract
# (docs/superpowers/specs/2026-07-12-jailyard-governance-crosswalk.md,
# "The Temporal Contract (uniform, exact-cutoff)"). It is DISTINCT from
# parse_ts, which exists for non-gating parsing only and wrongly accepts
# naive / date-only strings as UTC — never use parse_ts at an admission
# boundary.

_MONTH_ONLY_RE = re.compile(r"^\d{4}-\d{2}$")
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def admissible(ts_str, cutoff):
    """True iff ts_str is an exact tz-aware UTC instant at-or-before cutoff.

    Fail-closed exact-cutoff rule: admit iff an exact tz-aware instant
    ``<= cutoff``. Reject missing / malformed / naive / date-only / month-only
    — an exact-event projection cannot bucket a coarse timestamp. Offset-aware
    strings are converted to UTC; sub-second precision is preserved. ``cutoff``
    is a tz-aware UTC datetime, or None for all-evidence (admit any exact
    tz-aware instant). Month-granular comparison is banned.

    Deliberately does NOT delegate to parse_ts, which would wrongly accept
    naive/date-only strings as UTC and reopen the fail-open leak this replaces.
    """
    if not isinstance(ts_str, str):
        return False
    if _MONTH_ONLY_RE.match(ts_str):  # "2025-01" / "2025-13" -> reject
        return False
    if _DATE_ONLY_RE.match(ts_str):  # "2025-01-31" -> reject (no time-of-day)
        return False
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):  # malformed (incl. "2025-13-05T..")
        return False
    if dt.tzinfo is None:  # naive -> reject
        return False
    dt = dt.astimezone(timezone.utc)
    if cutoff is None:
        return True
    return dt <= cutoff


def month_key_strict(ts_str):
    """Canonical ``%Y-%m`` for an exact tz-aware instant, else raise ValueError.

    Fail-closed month bucketing: rejects missing / malformed / naive / date-only
    / month-only timestamps rather than slicing a bad ``ts[:7]`` into a filesystem
    path. Mirrors ``admissible``'s strictness. Used by split_chat_months to bucket
    chunks and to derive the canonical month set the rebuild's month-set gate
    asserts against (same parser on both sides -> expected and actual cannot drift).
    """
    if not isinstance(ts_str, str) or not ts_str:
        raise ValueError(f"missing timestamp: {ts_str!r}")
    if _MONTH_ONLY_RE.match(ts_str) or _DATE_ONLY_RE.match(ts_str):
        raise ValueError(f"non-instant (date/month-only) timestamp: {ts_str!r}")
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"malformed timestamp: {ts_str!r}") from exc
    if dt.tzinfo is None:
        raise ValueError(f"naive timestamp (no tz): {ts_str!r}")
    return dt.astimezone(timezone.utc).strftime("%Y-%m")


_SAFE_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def persona_slug(member):
    """Deterministic, filesystem-SAFE persona slug.

    Fail-closed: raises ValueError on any result that is empty or contains path
    separators / dots / unsafe characters, so a hostile or malformed member name
    can never escape the personas directory. Matches the historical slug for the
    12 real members ('~ Harlow' -> 'harlow', 'Ben Chodos' -> 'ben-chodos').
    """
    if not isinstance(member, str):
        raise ValueError(f"non-str persona member: {member!r}")
    slug = member.lower().strip().replace(" ", "-").replace("~", "").strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    if not _SAFE_SLUG_RE.fullmatch(slug):
        raise ValueError(f"unsafe persona slug {slug!r} from member {member!r}")
    return slug


def roster_persona_slugs(name_map):
    """Ordered {member: slug} over the roster (name_map keys); fail-closed on a
    slug collision (two members mapping to the same filename)."""
    mapping = {}
    seen = {}
    for member in name_map:
        slug = persona_slug(member)
        if slug in seen:
            raise ValueError(
                f"persona slug collision: {member!r} and {seen[slug]!r} both -> {slug!r}"
            )
        seen[slug] = member
        mapping[member] = slug
    return mapping


def save_json(path, data, indent=2, ensure_ascii=False, verbose=False):
    """Write data to a JSON file with consistent formatting.

    Creates parent directories if needed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
    if verbose:
        print(f"  Saved: {rel_to_root(path)}")


def save_json_canonical(path, data, verbose=False):
    """Canonical JSON write — sort_keys=True, ensure_ascii=False, indent=2.

    All new generators (Phase 1+ data work) use this helper to guarantee
    byte-identical output across runs (architect M6 mandate). NOTE: the
    pre-commit prettier hook may collapse short multi-line arrays onto one
    line — cosmetic only (values stay parse-identical). Re-extraction
    idempotency relies on input-hash manifests (e.g.
    nfl_games/_expanded_manifest.json), not byte parity with the committed,
    prettier-reformatted form.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    if verbose:
        print(f"  Saved (canonical): {rel_to_root(path)}")


# ---------------------------------------------------------------------------
# Identity / merge helpers
# ---------------------------------------------------------------------------


def normalize_username(name):
    """Strip ALL whitespace + casefold, for owner/username identity joins
    (e.g. the "kharlo w" vs "kharlow" drift)."""
    return re.sub(r"\s+", "", name or "").casefold()


def merge_allowlisted_fields(target, source, allowed_keys):
    """Shallow copy of target with only allowed_keys overwritten from source
    (when present); every other target key preserved verbatim."""
    merged = dict(target)
    for key in allowed_keys:
        if key in source:
            merged[key] = source[key]
    return merged


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

# Token budgets (local LLM generation defaults)
SECTION_TOKEN_BUDGETS = {
    "essay": 4096,
    "rankings": 6144,
    "confessionals": 2048,
    "mailbag": 2048,
    "bits": 1024,
}


# ---------------------------------------------------------------------------
# NFL stats (Sleeper undocumented endpoint)
# ---------------------------------------------------------------------------

SLEEPER_BASE = "https://api.sleeper.app"
NFL_STATS_URL = SLEEPER_BASE + "/stats/nfl/{season}/{week}?season_type=regular"
USER_AGENT = "JailyardDynasty/1.0"


def nfl_stats_path(season, week):
    """Path to cached NFL stats for a season-week."""
    return DATA_DIR / str(season) / f"nfl_stats_week{week}.json"


class NflStatsResponseError(ValueError):
    """Raised when the Sleeper stats response doesn't match expected shape."""


def validate_nfl_stats_response(payload, min_entries=0):
    """Validate a raw Sleeper stats response (list of player-week dicts).

    A minimum-viable response is a list of dicts, each with a `player_id`
    key. Empty lists are permitted (preseason / off-week) unless
    min_entries is set higher. Raises NflStatsResponseError with a
    descriptive message on any shape violation.
    """
    if not isinstance(payload, list):
        raise NflStatsResponseError(f"expected list, got {type(payload).__name__}")
    if len(payload) < min_entries:
        raise NflStatsResponseError(
            f"response has {len(payload)} entries, need at least {min_entries}"
        )
    for i, entry in enumerate(payload[:5]):  # sample first 5
        if not isinstance(entry, dict):
            raise NflStatsResponseError(
                f"entry {i} is {type(entry).__name__}, expected dict"
            )
        if entry.get("player_id") is None:
            raise NflStatsResponseError(f"entry {i} missing player_id field")
    return True


def fetch_nfl_stats(season, week, timeout=15, retries=3, delay=1):
    """Fetch per-player NFL stats from Sleeper's undocumented endpoint.

    Retries on transient network errors (URLError/HTTPError/TimeoutError)
    with exponential backoff matching fetch_sleeper.py's fetch_json pattern.
    Validates the response shape before returning — raises
    NflStatsResponseError if Sleeper returns something other than a list
    of player-week dicts.

    Returns a list of entries (one per player-week). Each entry has top-level
    keys: player_id, team, opponent, player (nested dict with first_name,
    last_name, position), stats (nested dict with numeric fields), game_id,
    week, season, etc.
    """
    url = NFL_STATS_URL.format(season=season, week=week)
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            validate_nfl_stats_response(payload)
            return payload
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
        ) as e:
            last_err = e
            if attempt < retries - 1:
                wait = delay * (2**attempt)
                print(f"  Retry {attempt + 1} after {wait}s: {e}")
                time.sleep(wait)
    # Exhausted retries — raise last network error
    raise last_err if last_err else RuntimeError(f"fetch_nfl_stats failed: {url}")


def load_nfl_stats_cache(season, week):
    """Load cached NFL stats. Returns None if cache file absent.

    Cache file is a dict {"stats": [...]} wrapping the raw Sleeper list.
    """
    return load_json(nfl_stats_path(season, week), warn=False)


# ---------------------------------------------------------------------------
# Momentum computation
# ---------------------------------------------------------------------------

MOMENTUM_LABELS = ("collapsing", "cooling", "steady", "hot", "surging")
MOMENTUM_WINDOW = 3


def _signed_streak(streak_str):
    """Convert a streak string like 'W3' or 'L2' to a signed integer.

    Clamped to ±5 so a W10 streak can't peg the momentum clamp and drown
    out margin/rank signals. Returns 0 for '—' or unknown.
    """
    if not streak_str or streak_str == "—":
        return 0
    kind = streak_str[0]
    try:
        count = int(streak_str[1:])
    except (ValueError, IndexError):
        return 0
    count = min(count, 5)
    if kind == "W":
        return count
    if kind == "L":
        return -count
    return 0


def _find_standing(prev_week, rid):
    """Find a roster's standings entry within a prev_weeks item."""
    for s in prev_week.get("standings", []):
        if s.get("roster_id") == rid:
            return s
    return None


def compute_momentum(prev_weeks, rid, current_week):
    """Compute a team's 3-week rolling momentum.

    Formula:
        score = (streak_signed * 0.35)
              + (avg_margin_last_3 / 25 * 0.35)
              + (rank_delta_last_3 * 0.30)

    Clamped to [-3, +3]. Week 1 (and teams with no prior data) returns
    {"score": 0, "label": "opening"}.

    Args:
        prev_weeks: list of prior weekN_data.json dicts (already extracted),
            in chronological order. Empty for week 1.
        rid: roster_id of the team to compute for.
        current_week: week number being extracted (for sentinel check).

    Returns:
        dict with keys "score" (float) and "label" (str).
    """
    if current_week == 1 or not prev_weeks:
        return {"score": 0, "label": "opening"}

    window = prev_weeks[-MOMENTUM_WINDOW:]
    snapshots = []
    for pw in window:
        s = _find_standing(pw, rid)
        if s:
            snapshots.append(s)

    if not snapshots:
        return {"score": 0, "label": "opening"}

    # Weeks 2-3 have insufficient data for a real 3-week rolling window.
    # Once we've confirmed the team has some prior data (snapshots non-empty),
    # emit an "early" sentinel so writer prose can skip trajectory framing.
    if current_week <= 3:
        return {"score": 0, "label": "early"}

    latest = snapshots[-1]
    streak_signed = _signed_streak(latest.get("streak", ""))

    margins = [s.get("margin_this_week", 0) for s in snapshots]
    avg_margin = sum(margins) / max(len(margins), 1)

    oldest_rank = snapshots[0].get("rank", 0)
    newest_rank = latest.get("rank", 0)
    rank_delta = oldest_rank - newest_rank

    score = (streak_signed * 0.35) + (avg_margin / 25.0 * 0.35) + (rank_delta * 0.30)
    score = max(-3.0, min(3.0, score))
    score = round(score, 2)

    if score < -1.5:
        label = "collapsing"
    elif score < -0.5:
        label = "cooling"
    elif score <= 0.5:
        label = "steady"
    elif score <= 1.5:
        label = "hot"
    else:
        label = "surging"

    return {"score": score, "label": label}
