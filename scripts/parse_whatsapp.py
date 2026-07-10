#!/usr/bin/env python
"""
parse_whatsapp.py — Deterministic WhatsApp chat parser for The Jailyard Dynasty.

Parses WhatsApp exported chat text into structured JSON.
No external dependencies — stdlib only (Python 3.9+).

Usage:
    python scripts/parse_whatsapp.py                         # defaults
    python scripts/parse_whatsapp.py --input path/to/file.txt
    python scripts/parse_whatsapp.py --stats                 # print stats only
"""

import argparse
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Force UTF-8 stdout on Windows (avoids cp1252 UnicodeEncodeError)
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from shared import NAME_MAP_PATH, REPO_ROOT

# WhatsApp line pattern: [M/D/YY, H:MM:SS AM/PM] Sender: message
# The date can be M/D/YY or MM/DD/YY (single or double digit month/day)
LINE_RE = re.compile(
    r"^\[(\d{1,2}/\d{1,2}/\d{2},\s\d{1,2}:\d{2}:\d{2}\s[AP]M)\]\s(.*)$"
)

# Sender separator — first ": " after the timestamp bracket
SENDER_RE = re.compile(r"^([^:]+):\s(.*)$", re.DOTALL)

# Media attachment
MEDIA_RE = re.compile(r"<attached:\s*(.+?)>")

# Edited marker
EDITED_MARKER = "<This message was edited>"

# Poll detection
POLL_PREFIX = "POLL:"

# @mention extraction — WhatsApp @mentions use phone numbers or display names.
# Match: @+1 234 567 8900 (phone) or @First Last (up to 2 words)
MENTION_RE = re.compile(r"@(\+?\d[\d\s\-]+\d|[A-Za-z~]\w*(?:\s[A-Za-z~]\w*)?)")

# Pacific timezone
TZ_PACIFIC = ZoneInfo("America/Los_Angeles")
TZ_UTC = timezone.utc

GROUP_NAME = "The Jailyard"
EXPORT_DATE = "2026-02-21"
PLATFORM_HISTORY = (
    "Migrated from iMessage to WhatsApp on 2023-09-07. "
    "League group chat predates this export."
)


def build_alias_map() -> dict[str, str]:
    """Build alias → canonical WhatsApp name map from name-map.json."""
    if not NAME_MAP_PATH.exists():
        return {}
    name_map = json.loads(NAME_MAP_PATH.read_text(encoding="utf-8"))
    alias_to_canonical = {}
    for canonical, info in name_map.items():
        for alias in info.get("aliases", []):
            alias_to_canonical[alias] = canonical
        # Also map real_name if it differs from canonical
        real = info.get("real_name", "")
        if real and real != canonical:
            alias_to_canonical[real] = canonical
    return alias_to_canonical


def parse_timestamp(raw: str) -> tuple[datetime, datetime]:
    """Parse WhatsApp timestamp string into (utc_dt, local_dt) pair."""
    # Format: M/D/YY, H:MM:SS AM/PM
    local_naive = datetime.strptime(raw, "%m/%d/%y, %I:%M:%S %p")
    local_dt = local_naive.replace(tzinfo=TZ_PACIFIC)
    utc_dt = local_dt.astimezone(TZ_UTC)
    return utc_dt, local_dt


def format_utc(dt: datetime) -> str:
    """ISO-8601 with trailing Z."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_local(dt: datetime) -> str:
    """ISO-8601 with UTC offset like -07:00 or -08:00."""
    return dt.isoformat()


def extract_mentions(text: str) -> list[str]:
    """Extract @mentions from message text."""
    return [m.strip() for m in MENTION_RE.findall(text)]


def parse_poll(text: str) -> dict | None:
    """Parse poll content if message starts with POLL:."""
    if not text.startswith(POLL_PREFIX):
        return None
    lines = text[len(POLL_PREFIX) :].strip().split("\n")
    if not lines:
        return None
    question = lines[0].strip()
    options = []
    # Poll options follow as lines, possibly with vote counts
    option_re = re.compile(r"^(.+?)(?:\s*\((\d+)\s*votes?\))?$")
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        m = option_re.match(line)
        if m:
            opt_text = m.group(1).strip()
            votes = int(m.group(2)) if m.group(2) else 0
            options.append({"text": opt_text, "votes": votes})
    return {"question": question, "options": options}


def parse_chat(input_path: Path) -> dict:
    """Parse WhatsApp chat export into structured data."""
    raw = input_path.read_text(encoding="utf-8")
    lines = raw.split("\n")

    alias_map = build_alias_map()

    messages = []
    current_msg = None

    for line in lines:
        match = LINE_RE.match(line)
        if match:
            # Flush previous message
            if current_msg is not None:
                messages.append(current_msg)

            ts_raw = match.group(1)
            rest = match.group(2)
            utc_dt, local_dt = parse_timestamp(ts_raw)

            sender_match = SENDER_RE.match(rest)
            if sender_match:
                # WhatsApp renders contact-less senders as "~ Name" (narrow
                # no-break space); name-map/identity files use a regular space.
                # Normalize all unicode spaces or Harlow/Patrick never resolve.
                sender = (
                    sender_match.group(1)
                    .replace(" ", " ")  # narrow no-break space
                    .replace(" ", " ")  # no-break space
                    .strip()
                )
                # Normalize aliases to canonical WhatsApp name
                sender = alias_map.get(sender, sender)
                text = sender_match.group(2)
                # WhatsApp uses the group name as "sender" for auto-messages
                if sender == GROUP_NAME:
                    is_system = True
                    sender = None
                else:
                    is_system = False
            else:
                # System message — no sender
                sender = None
                text = rest.strip()
                is_system = True

            current_msg = {
                "utc_dt": utc_dt,
                "local_dt": local_dt,
                "sender": sender,
                "text": text,
                "is_system": is_system,
            }
        else:
            # Continuation line — append to current message
            if current_msg is not None and line:
                current_msg["text"] += "\n" + line

    # Flush last message
    if current_msg is not None:
        messages.append(current_msg)

    # Build output messages
    output_messages = []
    senders = set()

    for idx, msg in enumerate(messages, start=1):
        text = msg["text"]

        # Check edited
        is_edited = EDITED_MARKER in text
        if is_edited:
            text = text.replace(EDITED_MARKER, "").strip()

        # Check media
        media_match = MEDIA_RE.search(text)
        media = media_match.group(1) if media_match else None

        # Check poll
        is_poll = text.startswith(POLL_PREFIX) if not msg["is_system"] else False
        poll_data = parse_poll(text) if is_poll else None

        # Extract mentions
        mentions = extract_mentions(text) if not msg["is_system"] else []

        if msg["sender"]:
            senders.add(msg["sender"])

        output_messages.append(
            {
                "id": idx,
                "timestamp_utc": format_utc(msg["utc_dt"]),
                "timestamp_local": format_local(msg["local_dt"]),
                "sender": msg["sender"],
                "text": text,
                "media": media,
                "is_system": msg["is_system"],
                "is_poll": is_poll,
                "poll_data": poll_data,
                "mentions": mentions,
                "is_edited": is_edited,
            }
        )

    # Metadata
    sorted_senders = sorted(senders)
    date_range = {}
    if output_messages:
        date_range = {
            "start": output_messages[0]["timestamp_utc"],
            "end": output_messages[-1]["timestamp_utc"],
        }

    metadata = {
        "group_name": GROUP_NAME,
        "export_date": EXPORT_DATE,
        "message_count": len(output_messages),
        "date_range": date_range,
        "timezone_source": "America/Los_Angeles",
        "platform_history": PLATFORM_HISTORY,
        "members": sorted_senders,
    }

    return {"metadata": metadata, "messages": output_messages}


def build_identity_chain(name_map_path: Path) -> dict:
    """Build identity chain bridging Sleeper roster_id <-> WhatsApp names."""
    name_map = json.loads(name_map_path.read_text(encoding="utf-8"))

    # Hard-coded Sleeper roster data (from spec)
    roster_data = {
        1: {
            "owner_id": "510013812276232192",
            "username": "GauchoTrain",
            "team": "The Boonist Monks",
        },
        2: {
            "owner_id": "575194626101170176",
            "username": "bchodos",
            "team": "Kittler on the Roof",
        },
        3: {
            "owner_id": "575406354368348160",
            "username": "kharlow",
            "team": "Burden of Etienne-y Woody",
        },
        4: {
            "owner_id": "575878107617718272",
            "username": "kevobucks",
            "team": "Noble FFT",
        },
        5: {
            "owner_id": "510215233736572928",
            "username": "KidBouzie",
            "team": "The Legion of Bouz",
        },
        6: {
            "owner_id": "415249306090479616",
            "username": "ToreroGaucho",
            "team": "Rasheeing the Scene",
        },
        7: {
            "owner_id": "792312710317572096",
            "username": "Chudders",
            "team": "Chudders Football Team",
        },
        8: {"owner_id": "792563831732838400", "username": "rango_", "team": "MHJTIME"},
        9: {
            "owner_id": "793977545186979840",
            "username": "Redrumsregrub",
            "team": "Father Time",
        },
        10: {
            "owner_id": "861064424906158080",
            "username": "bLaker24",
            "team": "General Ken-obi",
        },
        11: {
            "owner_id": "510254202180411392",
            "username": "zbcowan",
            "team": "Sleeping Giants",
        },
        12: {
            "owner_id": "865653448849391616",
            "username": "GrayskullXX",
            "team": "Ghastly Grayskull Gang",
        },
    }

    # Build reverse lookup: roster_id -> whatsapp_name
    roster_to_whatsapp = {}
    for wa_name, info in name_map.items():
        rid = info.get("roster_id")
        if rid is not None:
            roster_to_whatsapp[rid] = {
                "whatsapp_name": wa_name,
                "real_name": info["real_name"],
            }

    by_roster_id = {}
    by_whatsapp = {}
    by_team = {}

    for rid, sleeper in roster_data.items():
        wa_info = roster_to_whatsapp.get(rid, {})
        wa_name = wa_info.get("whatsapp_name", "")
        real_name = wa_info.get("real_name", "")

        by_roster_id[str(rid)] = {
            "owner_id": sleeper["owner_id"],
            "username": sleeper["username"],
            "team_name": sleeper["team"],
            "whatsapp_name": wa_name,
            "real_name": real_name,
        }

        if wa_name:
            by_whatsapp[wa_name] = {
                "roster_id": rid,
                "team_name": sleeper["team"],
                "sleeper_handle": sleeper["username"],
            }

        by_team[sleeper["team"]] = {
            "roster_id": rid,
            "whatsapp_name": wa_name,
            "sleeper_handle": sleeper["username"],
        }

    return {
        "by_roster_id": by_roster_id,
        "by_whatsapp": by_whatsapp,
        "by_team": by_team,
    }


def print_stats(data: dict) -> None:
    """Print verification stats."""
    meta = data["metadata"]
    messages = data["messages"]

    print(f"\n{'='*50}")
    print("  WhatsApp Chat Parse Results")
    print(f"{'='*50}")
    print(f"  Messages:        {meta['message_count']}")
    print(f"  Unique senders:  {len(meta['members'])}")
    if meta["date_range"]:
        print(f"  Date range:      {meta['date_range']['start']}")
        print(f"                   {meta['date_range']['end']}")
    print(f"  System messages: {sum(1 for m in messages if m['is_system'])}")
    print(f"  Edited messages: {sum(1 for m in messages if m['is_edited'])}")
    print(f"  Media messages:  {sum(1 for m in messages if m['media'])}")
    print(f"  Polls:           {sum(1 for m in messages if m['is_poll'])}")

    # Per-member counts
    counter = Counter(m["sender"] for m in messages if m["sender"])
    print("\n  Messages per member:")
    for sender, count in counter.most_common():
        print(f"    {sender:25s} {count:>5}")

    # Tripwire for the 2026-07 Harlow bug: unicode-space sender names never
    # resolve against name-map (narrow no-break space vs regular space).
    ghosts = [s for s in meta["members"] if chr(0x202F) in s or chr(0xA0) in s]
    if ghosts:
        print(
            "WARNING: " + str(len(ghosts)) + " sender name(s) contain unicode "
            "spaces and will NOT resolve against name-map: " + str(ghosts)
        )
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Parse WhatsApp chat export for The Jailyard Dynasty"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=REPO_ROOT / "chat" / "_chat.txt",
        help="Path to WhatsApp export text file (default: chat/_chat.txt)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "chat" / "parsed_messages.json",
        help="Output path for parsed messages (default: chat/parsed_messages.json)",
    )
    parser.add_argument(
        "--identity-output",
        type=Path,
        default=REPO_ROOT / "chat" / "identity_chain.json",
        help="Output path for identity chain (default: chat/identity_chain.json)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print stats only, don't write output files",
    )
    args = parser.parse_args()

    # Validate input
    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Parse chat
    print(f"Parsing: {args.input}")
    data = parse_chat(args.input)

    # Print stats always
    print_stats(data)

    if args.stats:
        return

    # Write parsed messages
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote: {args.output}")

    # Build and write identity chain
    name_map_path = REPO_ROOT / "content" / "chat" / "name-map.json"
    if name_map_path.exists():
        identity = build_identity_chain(name_map_path)
        args.identity_output.parent.mkdir(parents=True, exist_ok=True)
        args.identity_output.write_text(
            json.dumps(identity, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Wrote: {args.identity_output}")
    else:
        print(
            f"Warning: name-map not found at {name_map_path}, skipping identity chain",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
