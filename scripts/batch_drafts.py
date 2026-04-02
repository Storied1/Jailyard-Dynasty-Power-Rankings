#!/usr/bin/env python
"""
Batch Draft Generator v2 — orchestrates section-by-section local drafts.

Works with local_draft.py v2 (section-by-section generation). Supports:
  - Full 18-week runs (--all) or specific weeks
  - Redrafting shipped weeks (--redraft for fresh start on completed content)
  - Resume mode (--resume skips sections already in draft files)
  - Fast mode (--fast uses 8B for all sections)
  - Section-level progress tracking via state file
  - Estimated time based on section/model assignments

Usage:
    python scripts/batch_drafts.py --status               # status board only
    python scripts/batch_drafts.py                        # draft all unfinished weeks
    python scripts/batch_drafts.py --all                  # draft ALL 18 weeks (even shipped)
    python scripts/batch_drafts.py --weeks 7 8 9          # specific weeks
    python scripts/batch_drafts.py --fast                 # use 8B for everything
    python scripts/batch_drafts.py --resume               # skip already-drafted sections
    python scripts/batch_drafts.py --dry-run              # show plan without executing
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEEKS_DIR = REPO_ROOT / "content" / "weeks"
DRAFT_SCRIPT = REPO_ROOT / "scripts" / "local_draft.py"
STATE_FILE = WEEKS_DIR / ".batch_state.json"
PYTHON = sys.executable

# Time estimates per section (seconds) — based on model and token budget
# (section, heavy_model_secs, light_model_secs)
SECTION_TIMES = {
    "essay": (90, 30),
    "rankings": (120, 45),
    "confessionals": (20, 10),
    "mailbag": (25, 12),
    "bits": (15, 8),
}


def get_week_status():
    """Scan content/weeks/ and return status for each week."""
    status = {}
    for week in range(1, 19):
        draft_path = WEEKS_DIR / f"week{week}_draft.json"
        draft_sections = []
        if draft_path.exists():
            try:
                d = json.loads(draft_path.read_text(encoding="utf-8"))
                draft_sections = [
                    k
                    for k in d.keys()
                    if k in ("essay", "rankings", "confessionals", "mailbag", "bits")
                ]
            except (json.JSONDecodeError, OSError):
                pass

        status[week] = {
            "data": (WEEKS_DIR / f"week{week}_data.json").exists(),
            "chat": (WEEKS_DIR / f"week{week}_chat_context.json").exists(),
            "content": (WEEKS_DIR / f"week{week}_content.json").exists(),
            "draft": draft_path.exists(),
            "draft_sections": draft_sections,
            "html": (REPO_ROOT / f"week{week}.html").exists(),
        }
    return status


def print_status(status):
    """Print a compact pipeline status board."""
    print("\n" + "=" * 70)
    print("  JAILYARD WEEKLY COLUMN PIPELINE -- STATUS BOARD")
    print("=" * 70)
    print(
        f"  {'Week':<6} {'Data':<6} {'Chat':<6} {'Draft':<14} {'Content':<9} {'HTML':<6} {'Stage'}"
    )
    print("-" * 70)

    for week in range(1, 19):
        s = status[week]
        data = "Y" if s["data"] else "-"
        chat = "Y" if s["chat"] else "-"
        content = "Y" if s["content"] else "-"
        html = "Y" if s["html"] else "-"

        # Draft column shows section count
        if s["draft_sections"]:
            n = len(s["draft_sections"])
            draft = f"{n}/5"
        elif s["draft"]:
            draft = "Y"
        else:
            draft = "-"

        # Determine stage
        if s["html"]:
            stage = "SHIPPED"
        elif s["content"]:
            stage = "RENDER"
        elif s["draft"]:
            stage = "WRITE"
        elif s["data"] and s["chat"]:
            stage = "DRAFT"
        elif s["data"]:
            stage = "CHAT"
        else:
            stage = "DATA"

        stage_display = {
            "SHIPPED": "[SHIPPED]",
            "RENDER": "[RENDER ]",
            "WRITE": "[WRITE  ]",
            "DRAFT": "[DRAFT  ]",
            "CHAT": "[CHAT   ]",
            "DATA": "[DATA   ]",
        }

        print(
            f"  W{week:<5} {data:<6} {chat:<6} {draft:<14} {content:<9} {html:<6} {stage_display[stage]}"
        )

    # Summary
    shipped = sum(1 for w in status.values() if w["html"])
    drafted = sum(1 for w in status.values() if w["draft"])
    full_drafts = sum(1 for w in status.values() if len(w["draft_sections"]) == 5)
    ready = sum(
        1
        for w in status.values()
        if w["data"] and w["chat"] and not w["draft"] and not w["content"]
    )

    print("-" * 70)
    print(
        f"  Shipped: {shipped}/18 | Full drafts: {full_drafts} | "
        f"Partial drafts: {drafted - full_drafts} | Ready: {ready}"
    )
    print("=" * 70 + "\n")


def generate_draft(week, fast=False, resume=False, temperature=0.7):
    """Run local_draft.py v2 for a single week. Returns (success, elapsed)."""
    cmd = [
        PYTHON,
        str(DRAFT_SCRIPT),
        "--week",
        str(week),
        "--temperature",
        str(temperature),
    ]
    if fast:
        cmd.append("--fast")
    if resume:
        cmd.append("--resume")

    start = time.time()
    try:
        # v2 generates 5 sections (~4-5 min for 30B, ~2 min for 8B)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        elapsed = time.time() - start
        if result.returncode == 0:
            print(f"  [OK] Week {week} drafted in {elapsed:.0f}s")
            # Show last few lines of output
            lines = result.stdout.strip().split("\n")
            for line in lines[-4:]:
                if line.strip():
                    print(f"    {line.strip()}")
            return True, elapsed
        else:
            print(f"  [FAIL] Week {week} FAILED ({elapsed:.0f}s)")
            if result.stderr.strip():
                for line in result.stderr.strip().split("\n")[:3]:
                    print(f"    {line[:200]}")
            return False, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        print(f"  [FAIL] Week {week} TIMED OUT ({elapsed:.0f}s)")
        return False, elapsed


def estimate_time(weeks, fast=False):
    """Estimate total batch time based on section/model assignments."""
    per_week = sum(light if fast else heavy for heavy, light in SECTION_TIMES.values())
    total = per_week * len(weeks)
    return total


def save_state(results):
    """Save batch progress to state file."""
    state = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": [
            {"week": w, "success": s, "elapsed": round(e, 1)} for w, s, e in results
        ],
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Batch-generate local column drafts (v2)"
    )
    parser.add_argument(
        "--weeks",
        type=int,
        nargs="+",
        help="Specific weeks to draft (default: all missing)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Draft ALL 18 weeks, even ones with existing content/drafts",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Use 8B model for all sections (faster, lower quality)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip sections already present in existing draft files",
    )
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument(
        "--dry-run", action="store_true", help="Show plan without executing"
    )
    parser.add_argument("--status", action="store_true", help="Show status board only")
    args = parser.parse_args()

    status = get_week_status()

    if args.status:
        print_status(status)
        return

    # Determine which weeks to draft
    if args.weeks:
        weeks_to_draft = args.weeks
    elif args.all:
        # Everything with data+chat
        weeks_to_draft = [
            w for w in range(1, 19) if status[w]["data"] and status[w]["chat"]
        ]
    else:
        # Weeks with data+chat but no complete draft (5/5 sections)
        weeks_to_draft = [
            w
            for w in range(1, 19)
            if status[w]["data"]
            and status[w]["chat"]
            and len(status[w]["draft_sections"]) < 5
        ]

    if not weeks_to_draft:
        print("All weeks already have full drafts. Use --all to regenerate.")
        print_status(status)
        return

    print_status(status)

    est_secs = estimate_time(weeks_to_draft, args.fast)
    mode = "8B (fast)" if args.fast else "30B+8B (quality)"

    print(f"Weeks to draft: {', '.join(f'W{w}' for w in weeks_to_draft)}")
    print(f"Mode: {mode} | Temp: {args.temperature} | Resume: {args.resume}")
    print(
        f"Estimated time: ~{est_secs // 60}m {est_secs % 60}s "
        f"({len(weeks_to_draft)} weeks x 5 sections each)\n"
    )

    if args.dry_run:
        print("[DRY RUN] Would generate drafts for the above weeks.")
        return

    # Generate drafts sequentially (GPU can only do one at a time)
    results = []
    total_start = time.time()

    for i, week in enumerate(weeks_to_draft, 1):
        print(f"[{i}/{len(weeks_to_draft)}] Generating Week {week} draft...")
        success, elapsed = generate_draft(
            week, fast=args.fast, resume=args.resume, temperature=args.temperature
        )
        results.append((week, success, elapsed))
        save_state(results)

    total_elapsed = time.time() - total_start
    succeeded = sum(1 for _, s, _ in results if s)
    failed = sum(1 for _, s, _ in results if not s)

    print(f"\n{'=' * 50}")
    print(
        f"BATCH COMPLETE: {succeeded} succeeded, {failed} failed "
        f"in {total_elapsed // 60:.0f}m {total_elapsed % 60:.0f}s"
    )
    print(f"{'=' * 50}")

    if failed:
        failed_weeks = [w for w, s, _ in results if not s]
        print(f"Failed weeks: {', '.join(f'W{w}' for w in failed_weeks)}")
        print(
            "Re-run with: python scripts/batch_drafts.py --weeks "
            + " ".join(str(w) for w in failed_weeks)
            + " --resume"
        )

    # Show updated status
    print_status(get_week_status())


if __name__ == "__main__":
    main()
