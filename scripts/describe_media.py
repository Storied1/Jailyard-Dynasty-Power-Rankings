#!/usr/bin/env python
"""
Media vision analysis for Jailyard Dynasty WhatsApp media.

Sends images/video frames to Claude vision for description, tagging,
and humor classification. Progress is cached so re-runs skip completed batches.

Two backends:
  claude-cli (default) -- headless Claude Code (`claude -p`), billed against
      the Max SUBSCRIPTION (no API credits). Default model: claude-sonnet-5.
      On a usage-window limit it saves progress and exits cleanly; re-run to
      resume.
  api -- Anthropic API via ANTHROPIC_API_KEY (usage-billed). Default model:
      claude-haiku-4-5.

Dependencies: opencv-python-headless (+ anthropic for the api backend)
Input: chat/parsed_messages.json + media files in 'WhatsApp Chat - The Jailyard/'
Output: content/chat/media-catalog.json

Usage:
    python scripts/describe_media.py
    python scripts/describe_media.py --backend api
    python scripts/describe_media.py --model claude-opus-4-8
    python scripts/describe_media.py --batch-size 5
    python scripts/describe_media.py --dry-run
    python scripts/describe_media.py --limit 20
"""

import argparse
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Force UTF-8 stdout on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import anthropic
except ImportError:
    anthropic = None  # only required for --backend api; checked in create_client()

try:
    import cv2
except ImportError:
    print(
        "ERROR: opencv-python-headless required. Install with: pip install opencv-python-headless"
    )
    sys.exit(1)

from shared import (
    CHAT_DIR,
    CONTENT_CHAT_DIR,
    DESCRIPTION_BATCH_SIZE,
    JPEG_QUALITY,
    MAX_IMAGE_SIZE,
    REPO_ROOT,
)

PARSED_MESSAGES = CHAT_DIR / "parsed_messages.json"
MEDIA_DIR = REPO_ROOT / "WhatsApp Chat - The Jailyard"
PROGRESS_PATH = CONTENT_CHAT_DIR / ".media_progress.json"
OUTPUT_PATH = CONTENT_CHAT_DIR / "media-catalog.json"

API_MODEL_DEFAULT = "claude-haiku-4-5-20251001"  # gitleaks:allow -- model ID, not a key
CLI_MODEL_DEFAULT = "claude-sonnet-5"
MAX_TOKENS = 1024
RATE_LIMIT_RETRIES = 5
RATE_LIMIT_BASE_DELAY = 2.0
CLI_TIMEOUT_SEC = 900  # per claude -p invocation (a batch of images + reads)


# ── Image/Video Processing ───────────────────────────────────────────


def read_image_as_base64(
    path: Path, max_size: int = MAX_IMAGE_SIZE
) -> tuple[str, str] | None:
    """Read an image file, resize if needed, return (base64_data, media_type) or None."""
    try:
        img = cv2.imread(str(path))
        if img is None:
            return None
        h, w = img.shape[:2]
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
        _, buffer = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        b64 = base64.b64encode(buffer.tobytes()).decode("ascii")
        return b64, "image/jpeg"
    except Exception as e:
        print(f"    WARN: Failed to read image {path.name}: {e}")
        return None


def extract_video_frame(
    path: Path, target_sec: float = 1.0, max_size: int = MAX_IMAGE_SIZE
) -> tuple[str, str] | None:
    """Extract a frame from a video at target_sec, return (base64_data, media_type) or None."""
    try:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return None

        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        # Use target_sec or first frame if video is too short
        target_frame = int(min(target_sec, max(0, duration - 0.1)) * fps)
        target_frame = max(0, min(target_frame, total_frames - 1))

        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return None

        h, w = frame.shape[:2]
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

        _, buffer = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        )
        b64 = base64.b64encode(buffer.tobytes()).decode("ascii")
        return b64, "image/jpeg"
    except Exception as e:
        print(f"    WARN: Failed to extract frame from {path.name}: {e}")
        return None


def load_media_as_base64(path: Path) -> tuple[str, str] | None:
    """Load any media file as base64 image data."""
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg", ".webp", ".png"):
        return read_image_as_base64(path)
    elif suffix in (".mp4", ".mov"):
        return extract_video_frame(path)
    return None


def classify_media_type(filename: str) -> str:
    """Classify media as photo, gif_mp4, or video based on filename patterns."""
    fn = filename.upper()
    if "GIF" in fn:
        return "gif_mp4"
    elif "PHOTO" in fn or fn.endswith((".JPG", ".JPEG", ".WEBP", ".PNG")):
        return "photo"
    elif "VIDEO" in fn or fn.endswith((".MOV",)):
        return "video"
    elif fn.endswith(".MP4"):
        # WhatsApp: mp4 without GIF in name could be a short video
        return "gif_mp4"
    return "photo"


# ── AI Client ─────────────────────────────────────────────────────────


def create_client() -> "anthropic.Anthropic":
    """Create an Anthropic client. Requires ANTHROPIC_API_KEY env var."""
    if anthropic is None:
        print(
            "ERROR: anthropic package required for --backend api. pip install anthropic"
        )
        sys.exit(1)
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("ERROR: ANTHROPIC_API_KEY not set in environment.")
        sys.exit(1)
    return anthropic.Anthropic(api_key=key)


def parse_model_json_array(raw: str, n_items: int) -> list[dict]:
    """Parse a model response expected to be a JSON array of n_items objects.

    Tolerates markdown code fences and surrounding prose. On failure returns
    n_items 'Could not parse' placeholders (same convention both backends use).
    """
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[[\s\S]*\]", raw)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    return [
        {"description": "Could not parse", "tags": ["other"], "humor_type": "none"}
    ] * n_items


BATCH_SYSTEM_PROMPT = """You are analyzing images/GIF frames from a fantasy football league WhatsApp group chat called "The Jailyard Dynasty." These are memes, screenshots, reaction GIFs, and photos shared in group chat banter.

For each image, provide:
1. A concise description (1-2 sentences) of what the image shows
2. Tags (2-5) from: screenshot, meme, reaction_gif, stats, trophy, roster, standings, trash_talk, celebration, commiseration, news, sports, personal, trade, draft, lineup, injury, highlight, other
3. A humor_type if applicable: schadenfreude, flex, self_deprecation, absurdist, callback, roast, celebration, reaction, none

Respond with ONLY a JSON array, one object per image:
[{"description": "...", "tags": [...], "humor_type": "..."}]

Be specific about what you see — player names, team logos, stat lines, meme templates, etc. If it's a reaction GIF, describe the emotion/action. If it's a screenshot, note what app/site and what data is shown."""


def describe_batch(
    client: "anthropic.Anthropic", batch_items: list[dict], model: str
) -> list[dict]:
    """Send a batch of images to Claude for description (API backend)."""
    content = []
    for item in batch_items:
        b64, media_type = item["image_data"]
        content.append(
            {
                "type": "text",
                "text": f"Image {item['index']} (from {item['sender']}, {item['media_type']}):",
            }
        )
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64,
                },
            }
        )

    for attempt in range(RATE_LIMIT_RETRIES):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=BATCH_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
            )
            raw = response.content[0].text.strip()
            return parse_model_json_array(raw, len(batch_items))
        except anthropic.RateLimitError:
            delay = RATE_LIMIT_BASE_DELAY * (2**attempt)
            print(f"    Rate limited. Retrying in {delay:.0f}s...")
            time.sleep(delay)
        except anthropic.APIError as e:
            print(f"    API error: {e}")
            if attempt < RATE_LIMIT_RETRIES - 1:
                time.sleep(RATE_LIMIT_BASE_DELAY)
            else:
                return [
                    {
                        "description": f"API error: {e}",
                        "tags": ["other"],
                        "humor_type": "none",
                    }
                ] * len(batch_items)

    return [
        {"description": "Max retries exceeded", "tags": ["other"], "humor_type": "none"}
    ] * len(batch_items)


# ── Claude Code CLI backend (subscription-billed) ────────────────────


def find_claude_cli() -> str:
    """Resolve the claude CLI binary, or exit with guidance."""
    path = shutil.which("claude")
    if not path:
        print(
            "ERROR: `claude` CLI not found on PATH. The claude-cli backend runs\n"
            "headless Claude Code on your subscription. Install/login Claude Code,\n"
            "or use --backend api with ANTHROPIC_API_KEY."
        )
        sys.exit(1)
    return path


def describe_batch_cli(
    claude_bin: str, batch_items: list[dict], model: str
) -> list[dict] | None:
    """Describe a batch via headless Claude Code (`claude -p`).

    Stages the already-resized JPEG frames as temp files (uniform handling for
    photos AND video frames), asks Claude Code to Read each and return the
    JSON array. Runs with cwd=tempdir so no project context/MCP servers load.

    Returns None on a hard failure (likely a subscription usage-window limit)
    so the caller can save progress and exit cleanly instead of poisoning
    catalog entries.
    """
    # cwd is the stable %TEMP% root, NOT the per-batch dir: the claude child
    # process would otherwise hold the dir as its cwd and Windows couldn't
    # delete it. The batch dir is a child of cwd, so Read needs no --add-dir.
    with tempfile.TemporaryDirectory(
        prefix="jailyard-media-", ignore_cleanup_errors=True
    ) as tmpdir:
        lines = []
        for i, item in enumerate(batch_items):
            b64, _media_type = item["image_data"]
            img_path = Path(tmpdir) / f"img_{i}.jpg"
            img_path.write_bytes(base64.b64decode(b64))
            lines.append(
                f"Image {i} (from {item['sender']}, {item['media_type']}): {img_path}"
            )

        prompt = (
            BATCH_SYSTEM_PROMPT
            + "\n\nRead each of these image files and analyze them in order:\n"
            + "\n".join(lines)
            + "\n\nRespond with ONLY the JSON array, one object per image, same order."
        )

        cmd = [
            claude_bin,
            "-p",
            prompt,
            "--model",
            model,
            "--output-format",
            "json",
        ]
        for attempt in range(RATE_LIMIT_RETRIES):
            try:
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=CLI_TIMEOUT_SEC,
                    cwd=tempfile.gettempdir(),
                )
            except subprocess.TimeoutExpired:
                print(f"    CLI timeout ({CLI_TIMEOUT_SEC}s), attempt {attempt + 1}")
                continue

            envelope = None
            if res.stdout:
                try:
                    envelope = json.loads(res.stdout)
                except json.JSONDecodeError:
                    pass

            if (
                res.returncode == 0
                and isinstance(envelope, dict)
                and not envelope.get("is_error")
                and envelope.get("result")
            ):
                return parse_model_json_array(str(envelope["result"]), len(batch_items))

            err_text = ""
            if isinstance(envelope, dict):
                err_text = str(envelope.get("result", ""))
            err_text = (err_text or "") + (res.stderr or "")
            print(f"    CLI error (attempt {attempt + 1}): {err_text[:200]}")
            if "limit" in err_text.lower():
                # Usage-window limit: retrying in-process won't outlast the
                # window. Signal the caller to save progress and exit.
                return None
            time.sleep(RATE_LIMIT_BASE_DELAY * (2**attempt))

    return None


# ── Progress Management ──────────────────────────────────────────────


def load_progress() -> dict:
    """Load progress state from cache file."""
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"completed_ids": [], "items": []}


def save_progress(progress: dict):
    """Save progress state to cache file."""
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False)


# ── Main ─────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Describe Jailyard WhatsApp media using Claude vision"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DESCRIPTION_BATCH_SIZE,
        help=f"Images per API call (default: {DESCRIPTION_BATCH_SIZE})",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Count media without calling API"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Process only N items (for testing)"
    )
    parser.add_argument(
        "--reset", action="store_true", help="Reset progress and start over"
    )
    parser.add_argument(
        "--backend",
        choices=("claude-cli", "api"),
        default="claude-cli",
        help="claude-cli = headless Claude Code on the Max subscription (default); "
        "api = Anthropic API via ANTHROPIC_API_KEY",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"Model override (defaults: {CLI_MODEL_DEFAULT} for claude-cli, "
        f"{API_MODEL_DEFAULT} for api)",
    )
    args = parser.parse_args()

    model = args.model or (
        CLI_MODEL_DEFAULT if args.backend == "claude-cli" else API_MODEL_DEFAULT
    )

    # ── Load parsed messages ──
    if not PARSED_MESSAGES.exists():
        print(f"ERROR: {PARSED_MESSAGES} not found. Run parse_whatsapp.py first.")
        sys.exit(1)

    print(f"Loading: {PARSED_MESSAGES}")
    with open(PARSED_MESSAGES, encoding="utf-8") as f:
        raw = json.load(f)
    messages = raw.get("messages", raw) if isinstance(raw, dict) else raw

    # ── Find media messages ──
    media_items = []
    for msg in messages:
        media = msg.get("media")
        if not media or msg.get("is_system"):
            continue

        filename = media.strip()
        file_path = MEDIA_DIR / filename
        if not file_path.exists():
            # Try with common variations
            continue

        media_items.append(
            {
                "message_id": msg.get("id"),
                "filename": filename,
                "file_path": str(file_path),
                "media_type": classify_media_type(filename),
                "sender": msg.get("sender", "Unknown"),
                "timestamp_utc": msg.get("timestamp_utc", ""),
            }
        )

    # Count by type
    type_counts = {}
    for item in media_items:
        t = item["media_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"  Found {len(media_items)} media messages with existing files")
    print(f"  By type: {json.dumps(type_counts)}")

    if args.dry_run:
        print("\n  DRY RUN — no API calls made.")
        return

    # ── Load/reset progress ──
    if args.reset and PROGRESS_PATH.exists():
        PROGRESS_PATH.unlink()
        print("  Progress reset.")

    progress = load_progress()
    completed_ids = set(progress.get("completed_ids", []))
    existing_items = {item["message_id"]: item for item in progress.get("items", [])}

    remaining = [
        item for item in media_items if item["message_id"] not in completed_ids
    ]
    if args.limit:
        remaining = remaining[: args.limit]

    print(f"  Already completed: {len(completed_ids)}")
    print(f"  Remaining: {len(remaining)}")

    if not remaining:
        print("  All media already processed. Writing final catalog.")
        # Write final output from progress
        write_catalog(progress, media_items, type_counts)
        return

    # ── Create backend ──
    print(f"  Backend: {args.backend} | model: {model}")
    client = None
    claude_bin = None
    if args.backend == "api":
        client = create_client()
    else:
        claude_bin = find_claude_cli()

    # ── Process in batches ──
    batches = [
        remaining[i : i + args.batch_size]
        for i in range(0, len(remaining), args.batch_size)
    ]
    total_batches = len(batches)
    print(
        f"\n  Processing {len(remaining)} items in {total_batches} batches of {args.batch_size}..."
    )

    for bi, batch in enumerate(batches, 1):
        print(
            f"  [{bi}/{total_batches}] Processing {len(batch)} items...",
            end=" ",
            flush=True,
        )

        # Load images
        batch_with_images = []
        for idx, item in enumerate(batch):
            img_data = load_media_as_base64(Path(item["file_path"]))
            if img_data is None:
                # Store a placeholder for unreadable files
                existing_items[item["message_id"]] = {
                    "message_id": item["message_id"],
                    "filename": item["filename"],
                    "type": item["media_type"],
                    "sender": item["sender"],
                    "timestamp_utc": item["timestamp_utc"],
                    "description": "Unable to read file",
                    "tags": ["unreadable"],
                    "humor_type": "none",
                }
                completed_ids.add(item["message_id"])
                continue

            batch_with_images.append(
                {
                    "index": idx,
                    "image_data": img_data,
                    "sender": item["sender"],
                    "media_type": item["media_type"],
                    "item": item,
                }
            )

        if batch_with_images:
            if args.backend == "claude-cli":
                descriptions = describe_batch_cli(claude_bin, batch_with_images, model)
                if descriptions is None:
                    # Usage-window limit or persistent CLI failure: keep these
                    # items un-completed and exit cleanly -- re-run to resume.
                    progress = {
                        "completed_ids": sorted(completed_ids),
                        "items": list(existing_items.values()),
                    }
                    save_progress(progress)
                    print(
                        "\n  Stopping: Claude Code usage limit (or persistent CLI "
                        "error). Progress saved -- re-run this script after the "
                        "usage window resets to resume."
                    )
                    sys.exit(0)
            else:
                descriptions = describe_batch(client, batch_with_images, model)

            for bi_item, desc in zip(batch_with_images, descriptions):
                item = bi_item["item"]
                existing_items[item["message_id"]] = {
                    "message_id": item["message_id"],
                    "filename": item["filename"],
                    "type": item["media_type"],
                    "sender": item["sender"],
                    "timestamp_utc": item["timestamp_utc"],
                    "description": desc.get("description", ""),
                    "tags": desc.get("tags", []),
                    "humor_type": desc.get("humor_type", "none"),
                }
                completed_ids.add(item["message_id"])

        # Save progress after each batch
        progress = {
            "completed_ids": sorted(completed_ids),
            "items": list(existing_items.values()),
        }
        save_progress(progress)
        print(f"done ({len(completed_ids)} total)")

        # Rate limiting pause between batches
        if bi < total_batches:
            time.sleep(0.5)

    # ── Write final catalog ──
    write_catalog(progress, media_items, type_counts)


def write_catalog(progress: dict, media_items: list, type_counts: dict):
    """Write the final media-catalog.json from progress data."""
    items = sorted(progress.get("items", []), key=lambda x: x.get("message_id", 0))

    catalog = {
        "metadata": {
            "total_media": len(media_items),
            "processed": len(items),
            "by_type": type_counts,
        },
        "items": items,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"\n  Wrote: {OUTPUT_PATH}")
    print(f"  Total items: {len(items)}")

    # Quick stats
    tag_counts = {}
    humor_counts = {}
    for item in items:
        for tag in item.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        ht = item.get("humor_type", "none")
        humor_counts[ht] = humor_counts.get(ht, 0) + 1

    print(
        f"\n  Top tags: {json.dumps(dict(sorted(tag_counts.items(), key=lambda x: -x[1])[:10]))}"
    )
    print(f"  Humor types: {json.dumps(humor_counts)}")


if __name__ == "__main__":
    main()
