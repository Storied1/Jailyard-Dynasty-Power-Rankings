"""Decision-run receipts for deterministic and model runners. K3.2 of plan 562e90d.

The on-disk receipt attests COMPLETION, never intent: persist_run refuses an
OPEN run, and load_runs counts only receipts whose cell carries a seal --
sealless receipts are enumerated as orphans (crash debris), never evidence.
"""

import json
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.decision_history import write_json_once  # noqa: E402
    from scripts.fact_schema import fact_hash  # noqa: E402
except ImportError:  # pragma: no cover - direct-run fallback
    from decision_history import write_json_once  # noqa: E402
    from fact_schema import fact_hash  # noqa: E402

from shared import load_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNNER_CONFIG_PATH = ROOT / "content" / "governance" / "runner_config.json"

RUNNER_KINDS = {"deterministic", "model"}

_DETERMINISTIC_ONLY = ("code_hash", "config_hash", "input_hashes")
_MODEL_ONLY = (
    "provider",
    "model",
    "model_version",
    "reasoning",
    "tools_policy",
    "browsing",
    "budget",
    "retries",
    "sampling_policy",
    "prompt_hash",
    "rule_hashes",
)


@dataclass(frozen=True)
class DecisionRun:
    run_id: str
    runner_kind: str
    edition_id: str
    arm_id: str
    trial_id: int
    state_hash: str
    bundle_hash: str
    predecessor_decision_hash: str | None
    started_at: str
    labeling: str
    # Deterministic-only fields
    code_hash: str | None = None
    config_hash: str | None = None
    input_hashes: dict | None = None
    # Model-only fields
    provider: str | None = None
    model: str | None = None
    model_version: str | None = None
    reasoning: str | None = None
    tools_policy: str | None = None
    browsing: str | None = None
    budget: int | None = None
    retries: int | None = None
    sampling_policy: str | None = None
    prompt_hash: str | None = None
    rule_hashes: dict | None = None
    # §6 masking: the per-experiment salt is ON the receipt, so opaque tokens
    # are re-derivable from committed evidence alone.
    mask_salt: str | None = None
    # Sanitized transport provenance (K3.7): never credentials or tokens.
    transport: dict | None = None
    usage: dict | None = None
    # Closed-run fields -- null until close_run.
    ended_at: str | None = None
    output_decision_hash: str | None = None


def open_run(runner_kind, **kw):
    """Validate the field set for the declared runner_kind and return an OPEN
    run. Model-only fields on a deterministic run (and vice versa) are refused."""
    if runner_kind not in RUNNER_KINDS:
        raise ValueError(f"runner_kind must be one of {sorted(RUNNER_KINDS)}")
    required = _DETERMINISTIC_ONLY if runner_kind == "deterministic" else _MODEL_ONLY
    forbidden = _MODEL_ONLY if runner_kind == "deterministic" else _DETERMINISTIC_ONLY
    missing = [f for f in required if kw.get(f) is None]
    if missing:
        raise ValueError(f"{runner_kind} run requires {missing}")
    present = [f for f in forbidden if kw.get(f) is not None]
    if present:
        raise ValueError(f"{runner_kind} run must not carry {present}")
    edition_id = kw["edition_id"]
    if (
        not edition_id.endswith("preseason")
        and kw.get("predecessor_decision_hash") is None
    ):
        raise ValueError(
            "predecessor_decision_hash is mandatory outside preseason -- "
            "a non-preseason run with no lineage is an orphan judgment"
        )
    season = int(edition_id.split("-", 1)[0])
    if season == 2025 and kw.get("labeling") != "retrospective_backtest":
        raise ValueError(
            "every 2025 run REQUIRES labeling='retrospective_backtest' (design §6); "
            f"got {kw.get('labeling')!r}"
        )
    run_id = (
        "run-"
        + fact_hash(
            {
                k: kw.get(k)
                for k in (
                    "edition_id",
                    "arm_id",
                    "trial_id",
                    "started_at",
                    "state_hash",
                )
            }
        )[len("sha256:") :][:16]
    )
    return DecisionRun(run_id=run_id, runner_kind=runner_kind, **kw)


def close_run(run, output_decision_hash, ended_at, usage=None, transport=None):
    """Bind the output hash and completion instant. The closed record is what
    persist_run writes and seal() verifies."""
    if not output_decision_hash or not ended_at:
        raise ValueError("close_run requires output_decision_hash and ended_at")
    updates = {"output_decision_hash": output_decision_hash, "ended_at": ended_at}
    if usage is not None:
        updates["usage"] = usage
    if transport is not None:
        updates["transport"] = transport
    return replace(run, **updates)


def persist_run(run, root):
    """Write the CLOSED receipt via exclusive-create. Refuses an OPEN run: the
    on-disk receipt attests completion, never intent."""
    if not run.ended_at or not run.output_decision_hash:
        raise ValueError("persist_run refuses an OPEN run; close_run first")
    season = int(run.edition_id.split("-", 1)[0])
    path = (
        Path(root)
        / f"{season}"
        / run.arm_id
        / f"trial{run.trial_id}"
        / f"{run.edition_id}.run.json"
    )
    write_json_once(path, asdict(run))
    return path


def load_runs(root):
    """Glob *.run.json -- its own suffix, never *.json. Returns (runs, orphans):
    `runs` are receipts whose cell carries a seal; `orphans` are sealless
    receipts enumerated explicitly -- invisible as evidence, impossible to lose
    silently."""
    root = Path(root)
    runs, orphans = [], []
    for p in sorted(root.glob("*/*/*/*.run.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        record = DecisionRun(**doc)
        sealed = p.with_name(p.name.replace(".run.json", ".seal.json")).exists()
        (runs if sealed else orphans).append(record)
    return runs, orphans


def runner_config(arm_id):
    """The model-arm configuration block. One block for all four model arms --
    identical configuration is what isolates data-layer lift."""
    doc = load_json(RUNNER_CONFIG_PATH, required=True)
    if arm_id == "record_points":
        raise ValueError("record_points is deterministic; it has no provider config")
    return doc["model_arms"]
