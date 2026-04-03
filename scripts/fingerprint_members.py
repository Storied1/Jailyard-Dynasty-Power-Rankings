#!/usr/bin/env python
"""
Quantitative fingerprinting of Jailyard Dynasty WhatsApp members.

Computes per-member behavioral stats from parsed chat messages.
Stdlib only — no external deps, no AI, no pip.

Usage:
    python scripts/fingerprint_members.py
    python scripts/fingerprint_members.py --pretty
    python scripts/fingerprint_members.py --input path/to/parsed_messages.json

Output: content/chat/fingerprints.json
"""

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 stdout on Windows (avoids cp1252 UnicodeEncodeError)
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from shared import (
    REPO_ROOT,
    CHAT_DIR,
    CONTENT_CHAT_DIR,
    CONVERSATION_GAP_SEC,
    REPLY_WINDOW_SEC,
    UPPERCASE_THRESHOLD,
    DISTINCTIVE_WORD_RATIO,
    VOWEL_RATIO_MIN,
    DISTINCTIVE_WORD_MIN_COUNT,
    DISTINCTIVE_WORDS_KEEP,
)

DEFAULT_INPUT = CHAT_DIR / "parsed_messages.json"
DEFAULT_OUTPUT = CONTENT_CHAT_DIR / "fingerprints.json"

# Emoji regex — matches most Unicode emoji ranges
EMOJI_RE = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f680-\U0001f6ff"  # transport & map
    "\U0001f1e0-\U0001f1ff"  # flags
    "\U00002702-\U000027b0"  # dingbats
    "\U000024c2-\U0001f251"  # enclosed characters
    "\U0001f900-\U0001f9ff"  # supplemental symbols
    "\U0001fa00-\U0001fa6f"  # chess symbols
    "\U0001fa70-\U0001faff"  # symbols extended-A
    "\U00002600-\U000026ff"  # misc symbols
    "\U0000fe00-\U0000fe0f"  # variation selectors
    "\U0000200d"  # zero width joiner
    "\U0000203c-\U00003299"  # misc
    "]+",
    flags=re.UNICODE,
)

# Common English stopwords — compact list
STOPWORDS = frozenset(
    "a an the and or but is it its in on at to for of by with as this that "
    "was were be been being have has had do does did will would shall should "
    "can could may might must not no nor so if then than too also just about "
    "up out off over after before into through during between each other some "
    "all any both more most such only very much many well still back even new "
    "now way long get make like i me my we us our you your he him his she her "
    "they them their what which who whom how when where why there here these "
    "those am are from just been don't i'm it's he's she's we're they're "
    "you're i'll we'll they'll you'll can't won't didn't doesn't isn't aren't "
    "wasn't weren't hasn't haven't hadn't couldn't wouldn't shouldn't let's "
    "that's there's here's who's what's how's lol haha yeah ok oh hey yo im "
    "ur gonna gotta lmao bruh bro dude man got got like really think know right "
    "one two said going time thing people good first week game day go come see "
    "say want need take look let big".split()
)

# Word tokenizer
WORD_RE = re.compile(r"[a-zA-Z']+")


def parse_ts(ts_str):
    """Parse ISO-8601 to UTC datetime."""
    if not ts_str:
        return None
    s = ts_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def extract_emojis(text):
    """Return list of emoji strings found in text."""
    return EMOJI_RE.findall(text)


def tokenize(text):
    """Lowercase word tokenization."""
    return [w.lower() for w in WORD_RE.findall(text) if len(w) > 1]


def compute_fingerprints(messages):
    """Compute per-member fingerprints from parsed messages."""

    # ── Collect raw data per member ──
    member_msgs = defaultdict(list)  # sender -> [msg]
    member_texts = defaultdict(list)  # sender -> [text]
    member_words = defaultdict(list)  # sender -> [word, word, ...]
    member_emojis = defaultdict(list)  # sender -> [emoji, ...]
    member_hours = defaultdict(list)  # sender -> [hour, ...]
    member_days = defaultdict(list)  # sender -> [weekday, ...]
    member_months = defaultdict(Counter)  # sender -> Counter(YYYY-MM)
    member_media = defaultdict(lambda: {"photo": 0, "gif_mp4": 0, "video": 0})
    member_lengths_chars = defaultdict(list)
    member_lengths_words = defaultdict(list)
    member_reply_targets = defaultdict(Counter)  # sender -> Counter(mentioned_sender)
    member_mentions_of = defaultdict(Counter)
    member_convo_starts = defaultdict(int)

    all_senders = set()
    prev_sender = None
    prev_ts = None

    for msg in messages:
        sender = msg.get("sender")
        if not sender or msg.get("is_system"):
            prev_sender = None
            continue

        all_senders.add(sender)
        text = msg.get("text", "")
        media = msg.get("media")
        ts = parse_ts(msg.get("timestamp_utc"))

        member_msgs[sender].append(msg)
        member_texts[sender].append(text)

        # Timing
        if ts:
            member_hours[sender].append(ts.hour)
            member_days[sender].append(ts.weekday())
            month_key = ts.strftime("%Y-%m")
            member_months[sender][month_key] += 1

        # Text stats
        words = tokenize(text)
        member_words[sender].extend(words)
        member_lengths_chars[sender].append(len(text))
        member_lengths_words[sender].append(len(words))

        # Emojis
        emojis = extract_emojis(text)
        member_emojis[sender].extend(emojis)

        # Media classification
        if media:
            fname = media.lower()
            if "gif" in fname or fname.endswith(".mp4"):
                member_media[sender]["gif_mp4"] += 1
            elif fname.endswith((".jpg", ".jpeg", ".webp", ".png")):
                member_media[sender]["photo"] += 1
            elif fname.endswith((".mov", ".avi")):
                member_media[sender]["video"] += 1

        # Conversation starter detection (gap > 30 min from previous message)
        if ts and prev_ts:
            gap_seconds = (ts - prev_ts).total_seconds()
            if gap_seconds > CONVERSATION_GAP_SEC:
                member_convo_starts[sender] += 1
        elif prev_ts is None:
            member_convo_starts[sender] += 1

        # Mentions tracking (via @mentions in text)
        mentions = msg.get("mentions", [])
        for m in mentions:
            member_mentions_of[sender][m] += 1

        # Reply-to approximation: if posting within 2 min of someone else, consider it a "reply"
        if ts and prev_ts and prev_sender and prev_sender != sender:
            gap = (ts - prev_ts).total_seconds()
            if gap < REPLY_WINDOW_SEC:
                member_reply_targets[sender][prev_sender] += 1

        prev_sender = sender
        prev_ts = ts

    # ── Compute group-level word frequencies ──
    all_words = []
    for words in member_words.values():
        all_words.extend(words)
    total_group_words = len(all_words)
    group_word_freq = Counter(all_words)

    # ── Build fingerprints ──
    fingerprints = {}
    total_convo_starts = sum(member_convo_starts.values()) or 1

    for sender in sorted(all_senders):
        msgs = member_msgs[sender]
        texts = member_texts[sender]
        words = member_words[sender]
        total_msgs = len(msgs)
        total_words_member = len(words)

        # ── Volume ──
        months_active = member_months[sender]
        num_months = len(months_active) or 1
        avg_chars = sum(member_lengths_chars[sender]) / total_msgs if total_msgs else 0
        avg_words = sum(member_lengths_words[sender]) / total_msgs if total_msgs else 0
        longest_msg = (
            max(member_lengths_chars[sender]) if member_lengths_chars[sender] else 0
        )

        volume = {
            "total_messages": total_msgs,
            "messages_per_month": round(total_msgs / num_months, 1),
            "avg_length_chars": round(avg_chars, 1),
            "avg_length_words": round(avg_words, 1),
            "longest_message_chars": longest_msg,
        }

        # ── Timing ──
        hour_counter = Counter(member_hours[sender])
        peak_hour_hist = [hour_counter.get(h, 0) for h in range(24)]
        day_counter = Counter(member_days[sender])
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        dow_hist = {day_names[d]: day_counter.get(d, 0) for d in range(7)}

        late_night = sum(hour_counter.get(h, 0) for h in range(0, 5))
        late_night_pct = round(100 * late_night / total_msgs, 1) if total_msgs else 0

        timing = {
            "peak_hour_histogram": peak_hour_hist,
            "day_of_week": dow_hist,
            "late_night_pct": late_night_pct,
            "peak_hour": (
                max(range(24), key=lambda h: hour_counter.get(h, 0))
                if total_msgs
                else None
            ),
        }

        # ── Style ──
        emoji_counter = Counter(member_emojis[sender])
        top_emojis = [
            {"emoji": e, "count": c} for e, c in emoji_counter.most_common(10)
        ]
        emoji_freq = (
            round(len(member_emojis[sender]) / total_msgs, 2) if total_msgs else 0
        )

        # Caps ratio: fraction of messages with >50% uppercase alpha chars
        caps_msgs = 0
        question_msgs = 0
        exclamation_msgs = 0
        for t in texts:
            alpha = [c for c in t if c.isalpha()]
            if (
                alpha
                and sum(1 for c in alpha if c.isupper()) / len(alpha)
                > UPPERCASE_THRESHOLD
            ):
                caps_msgs += 1
            if "?" in t:
                question_msgs += 1
            if "!" in t:
                exclamation_msgs += 1

        style = {
            "emoji_top_10": top_emojis,
            "emoji_frequency": emoji_freq,
            "caps_ratio": round(caps_msgs / total_msgs, 3) if total_msgs else 0,
            "question_ratio": round(question_msgs / total_msgs, 3) if total_msgs else 0,
            "exclamation_ratio": (
                round(exclamation_msgs / total_msgs, 3) if total_msgs else 0
            ),
        }

        # ── Vocabulary ──
        word_counter = Counter(words)
        unique_words = len(word_counter)
        avg_word_len = (
            round(sum(len(w) for w in words) / total_words_member, 2)
            if total_words_member
            else 0
        )

        # Distinctive words via frequency ratio
        distinctive = []
        vowels = set("aeiou")
        if total_words_member > 0 and total_group_words > 0:
            for word, count in word_counter.items():
                if (
                    word in STOPWORDS
                    or count < DISTINCTIVE_WORD_MIN_COUNT
                    or len(word) < 3
                    or len(word) > 15
                ):
                    continue
                # Filter garbled strings (URL fragments, encryption)
                vowel_count = sum(1 for c in word if c in vowels)
                if vowel_count == 0 or vowel_count / len(word) < VOWEL_RATIO_MIN:
                    continue
                member_rate = count / total_words_member
                group_rate = group_word_freq[word] / total_group_words
                if group_rate > 0:
                    ratio = member_rate / group_rate
                    if ratio >= DISTINCTIVE_WORD_RATIO:
                        distinctive.append(
                            {
                                "word": word,
                                "count": count,
                                "ratio": round(ratio, 1),
                            }
                        )
            distinctive.sort(key=lambda x: x["ratio"], reverse=True)
            distinctive = distinctive[:DISTINCTIVE_WORDS_KEEP]

        vocabulary = {
            "unique_words": unique_words,
            "avg_word_length": avg_word_len,
            "distinctive_words": distinctive,
        }

        # ── Media ──
        media_stats = dict(member_media[sender])
        total_media = sum(media_stats.values())
        media_text_ratio = round(total_media / total_msgs, 3) if total_msgs else 0

        media_out = {
            "photos_sent": media_stats.get("photo", 0),
            "gifs_videos_sent": media_stats.get("gif_mp4", 0)
            + media_stats.get("video", 0),
            "media_to_text_ratio": media_text_ratio,
        }

        # ── Social ──
        reply_dist = dict(member_reply_targets[sender].most_common(12))
        mention_dist = dict(member_mentions_of[sender].most_common(12))
        convo_start_ratio = round(member_convo_starts[sender] / total_convo_starts, 3)

        social = {
            "reply_to_distribution": reply_dist,
            "mention_frequency": mention_dist,
            "conversation_starter_ratio": convo_start_ratio,
        }

        fingerprints[sender] = {
            "volume": volume,
            "timing": timing,
            "style": style,
            "vocabulary": vocabulary,
            "media": media_out,
            "social": social,
        }

    return {
        "metadata": {
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_messages": len(messages),
            "member_count": len(fingerprints),
            "analysis_version": "1.0",
        },
        "members": fingerprints,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Quantitative fingerprinting of Jailyard WhatsApp members"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Path to parsed_messages.json (default: {DEFAULT_INPUT.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT.relative_to(REPO_ROOT)})",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")

    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: {args.input} not found. Run parse_whatsapp.py first.")
        sys.exit(1)

    print(f"Loading: {args.input}")
    with open(args.input, encoding="utf-8") as f:
        raw = json.load(f)

    messages = raw.get("messages", raw) if isinstance(raw, dict) else raw
    print(f"  {len(messages):,} messages")

    print("Computing fingerprints...")
    result = compute_fingerprints(messages)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    indent = 2 if args.pretty else None
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=indent, ensure_ascii=False)
    print(f"Wrote: {args.output}")

    # Print summary
    print(f"\n{'='*50}")
    print(f"  Fingerprint Summary ({result['metadata']['member_count']} members)")
    print(f"{'='*50}")
    for name, fp in sorted(
        result["members"].items(),
        key=lambda x: x[1]["volume"]["total_messages"],
        reverse=True,
    ):
        v = fp["volume"]
        t = fp["timing"]
        s = fp["style"]
        voc = fp["vocabulary"]
        top_words = ", ".join(w["word"] for w in voc["distinctive_words"][:5])
        print(
            f"  {name:25s} | {v['total_messages']:>5} msgs | "
            f"peak hr {t['peak_hour'] or '?':>2} | "
            f"emoji {s['emoji_frequency']:.2f}/msg | "
            f"distinctive: {top_words}"
        )
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
