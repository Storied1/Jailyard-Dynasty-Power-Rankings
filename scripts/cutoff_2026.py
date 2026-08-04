"""Kickoff qualification + cutoff receipt for the 2026 safeguard (task A4).

Contract: docs/superpowers/plans/2026-08-03-jailyard-p-only-fallback.md
  S4 cutoff-qualification receipt; I17 (kickoff derived from a VERIFIED
  nfl_schedules envelope with venue-timezone conversion — never hardcoded
  in production), I18 (receipt binds game id, source locator, envelope
  hash and derivation version), R1 (preseason = kickoff - 7 days; preview
  strictly before kickoff), and the I42 unit surface: downstream code
  reads cutoffs ONLY through load_cutoff_receipt, which re-verifies the
  receipt hash on every read.

nflverse publishes gameday/gametime in US Eastern local time regardless
of venue; the venue-normalized conversion is therefore Eastern -> UTC via
the IANA zone (DST-correct), not a fixed offset.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from scripts.capture_2026 import (
        PUBLIC_CAPTURE_ROOT,  # noqa: E402
        RECEIPTS_ROOT,
        CaptureError,
        _utc_compact,
        canonical_bytes,
        load_json_bytes_strict,
        sha256_hex,
        verify_envelope,
    )
except ImportError:  # pragma: no cover — direct-run fallback
    from capture_2026 import (
        PUBLIC_CAPTURE_ROOT,
        RECEIPTS_ROOT,  # noqa: E402
        CaptureError,
        _utc_compact,
        canonical_bytes,
        load_json_bytes_strict,
        sha256_hex,
        verify_envelope,
    )

DERIVATION_VERSION = "cutoff_derivation_v1"
SCHEDULE_LOCAL_TZ = ZoneInfo("America/New_York")

CUTOFF_RECEIPT_FIELDS = (
    "season",
    "kickoff_utc",
    "kickoff_game_id",
    "kickoff_source_locator",
    "kickoff_source_envelope_sha256",
    "derivation_version",
    "preseason_cutoff_utc",
    "preview_cutoff_utc",
    "qualified_at",
    "receipt_sha256",
)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _game_kickoff_utc(game: dict) -> datetime:
    """One game's kickoff instant: local Eastern gameday+gametime -> UTC."""
    try:
        local = datetime.strptime(
            f"{game['gameday']} {game['gametime']}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=SCHEDULE_LOCAL_TZ)
    except (KeyError, ValueError, TypeError) as exc:
        raise CaptureError(
            f"unparseable kickoff for game {game.get('game_id')!r}: {exc}"
        ) from exc
    return local.astimezone(timezone.utc)


def qualify_kickoff(schedules_envelope_path) -> dict:
    """First regular-season kickoff, derived from a VERIFIED envelope (I17)."""
    path = Path(schedules_envelope_path)
    ok, errors = verify_envelope(path)
    if not ok:
        raise CaptureError(
            f"schedules envelope failed verification, not a qualification source: "
            f"{'; '.join(errors)}"
        )
    envelope = load_json_bytes_strict(path.read_bytes())
    games = envelope["payload"].get("games")
    if not isinstance(games, list) or not games:
        raise CaptureError("schedules payload has no games")

    regular = [g for g in games if g.get("game_type") == "REG"]
    if not regular:
        raise CaptureError("no regular-season games in the schedules payload")
    first_week = min(g["week"] for g in regular)
    openers = [g for g in regular if g["week"] == first_week]

    # earliest UTC instant wins; game_id breaks a same-instant tie deterministically
    kickoff_game = min(openers, key=lambda g: (_game_kickoff_utc(g), g["game_id"]))
    kickoff_utc = _game_kickoff_utc(kickoff_game)
    return {
        "kickoff_utc": _iso_z(kickoff_utc),
        "kickoff_game_id": kickoff_game["game_id"],
        "kickoff_source_locator": envelope["locator"],
        "kickoff_source_envelope_sha256": envelope["envelope_sha256"],
    }


def derive_cutoffs(kickoff_utc: datetime) -> tuple[datetime, datetime]:
    """R1: preseason = kickoff - 7 days; preview = strictly before kickoff."""
    return kickoff_utc - timedelta(days=7), kickoff_utc - timedelta(seconds=1)


def compute_receipt_sha256(receipt: dict) -> str:
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    return sha256_hex(canonical_bytes(body))


def build_cutoff_receipt(schedules_envelope_path, *, now=None) -> dict:
    qualified = qualify_kickoff(schedules_envelope_path)
    kickoff = datetime.fromisoformat(qualified["kickoff_utc"].replace("Z", "+00:00"))
    preseason, preview = derive_cutoffs(kickoff)
    qualified_at = now if now is not None else datetime.now(timezone.utc)
    receipt = {
        "season": 2026,
        "kickoff_utc": qualified["kickoff_utc"],
        "kickoff_game_id": qualified["kickoff_game_id"],
        "kickoff_source_locator": qualified["kickoff_source_locator"],
        "kickoff_source_envelope_sha256": qualified["kickoff_source_envelope_sha256"],
        "derivation_version": DERIVATION_VERSION,
        "preseason_cutoff_utc": _iso_z(preseason),
        "preview_cutoff_utc": _iso_z(preview),
        "qualified_at": _iso_z(qualified_at),
    }
    receipt["receipt_sha256"] = compute_receipt_sha256(receipt)
    return receipt


def write_cutoff_receipt(receipt: dict, receipts_root=None) -> Path:
    root = Path(receipts_root) if receipts_root is not None else RECEIPTS_ROOT
    compact = _utc_compact(
        datetime.fromisoformat(receipt["qualified_at"].replace("Z", "+00:00"))
    )
    target = root / f"cutoff_{compact}.json"
    if target.exists():
        raise CaptureError(f"append-only receipts: {target} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as f:
        f.write(canonical_bytes(receipt))
    return target


def load_cutoff_receipt(path) -> dict:
    """The ONLY sanctioned way to read cutoffs downstream (I42).

    Re-verifies receipt_sha256 and field presence on every read, so a
    tampered receipt fails closed instead of quietly steering a cutoff.
    """
    path = Path(path)
    if not path.exists():
        raise CaptureError(f"cutoff receipt missing: {path}")
    receipt = load_json_bytes_strict(path.read_bytes())
    missing = [f for f in CUTOFF_RECEIPT_FIELDS if f not in receipt]
    if missing:
        raise CaptureError(f"cutoff receipt missing fields: {missing}")
    expected = compute_receipt_sha256(receipt)
    if receipt["receipt_sha256"] != expected:
        raise CaptureError(
            f"cutoff receipt hash mismatch: recorded {receipt['receipt_sha256']}, "
            f"recomputed {expected}"
        )
    return receipt


def latest_cutoff_receipt_path(receipts_root=None):
    root = Path(receipts_root) if receipts_root is not None else RECEIPTS_ROOT
    if not root.is_dir():
        return None
    candidates = sorted(root.glob("cutoff_*.json"), reverse=True)
    return candidates[0] if candidates else None


def _latest_schedules_envelope_path(public_root=None):
    root = Path(public_root) if public_root is not None else PUBLIC_CAPTURE_ROOT
    source_dir = root / "nfl_schedules"
    if not source_dir.is_dir():
        return None
    for path in sorted(source_dir.glob("*.json"), reverse=True):
        ok, _ = verify_envelope(path)
        if ok:
            return path
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="cutoff_2026.py",
        description=(
            "Qualify the 2026 kickoff from the latest verified nfl_schedules "
            "envelope and write the cutoff-qualification receipt (S4)."
        ),
    )
    parser.add_argument("--season", type=int, help="season (2026 only)")
    parser.add_argument(
        "--write-receipt",
        action="store_true",
        help="derive cutoffs and write the receipt under data/captures/2026/_receipts/",
    )
    args = parser.parse_args(argv)

    if args.season is not None and args.season != 2026:
        print(
            f"this module is 2026-scoped; got --season {args.season}", file=sys.stderr
        )
        return 2

    if args.write_receipt:
        envelope_path = _latest_schedules_envelope_path()
        if envelope_path is None:
            print(
                "no verified nfl_schedules envelope in the capture store; "
                "run capture_2026.py --season 2026 --component nfl_schedules first",
                file=sys.stderr,
            )
            return 1
        try:
            receipt = build_cutoff_receipt(envelope_path)
            target = write_cutoff_receipt(receipt)
        except CaptureError as exc:
            print(f"cutoff qualification failed closed: {exc}", file=sys.stderr)
            return 1
        print(f"cutoff receipt: {target}")
        print(f"  kickoff  {receipt['kickoff_utc']}  ({receipt['kickoff_game_id']})")
        print(f"  preseason cutoff {receipt['preseason_cutoff_utc']}")
        print(f"  preview cutoff   {receipt['preview_cutoff_utc']}")
        return 0

    parser.print_usage(sys.stderr)
    print("cutoff_2026.py: no action requested", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
