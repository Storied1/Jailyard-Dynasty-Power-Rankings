#!/usr/bin/env python
"""Deterministic MAP phase: extract structured analytics from monthly chat chunks.

No AI calls. Pure computational extraction using heuristics, regex, and stats.
Produces MAP cache files compatible with the analyze_chat.py schema.

Usage:
    python scripts/map_chat_deterministic.py              # all months
    python scripts/map_chat_deterministic.py --month 2024-03  # single month
"""

import re
import sys
from collections import Counter, defaultdict
from datetime import timedelta

from shared import (
    CONSENSUS_MIN_SENDERS,
    CONSENSUS_WINDOW_SIZE,
    MAP_CACHE_DIR,
    NAME_MAP_PATH,
    RAPID_BURST_SEC,
    load_json,
    parse_ts,
    save_json,
)

# --- Prediction / hot-take detection patterns ---
PREDICTION_PATTERNS = [
    (r"\bi ('|)bet\b", "bet"),
    (r"\bguarantee\b", "guarantee"),
    (r"\bcalling it now\b", "prediction"),
    (r"\bmark my words\b", "prediction"),
    (r"\bprediction[:\s]", "prediction"),
    (r"\bhot take[:\s]", "hot_take"),
    (r"\bhe('|.)?s? *(gonna|going to|will) *(be|finish|end up)\b", "prediction"),
    (r"\b(over|under) (\d+) (wins|points|tds|touchdowns)\b", "prediction"),
    (r"\bwill win (the )?(chip|championship|league|title|ship)\b", "prediction"),
    (r"\bworst (team|roster|squad)\b", "hot_take"),
    (r"\bbest (team|roster|squad)\b", "hot_take"),
    (r"\bbust\b.*\b(this year|this season|202\d)\b", "hot_take"),
    (r"\bsleeper\b.*\b(this year|this season|202\d)\b", "hot_take"),
    (r"\bflop\b", "hot_take"),
    (r"\bfraud\b", "hot_take"),
    (r"\b(easy|free|guaranteed) (dub|win|money)\b", "guarantee"),
    (r"\bno chance\b", "hot_take"),
    (r"\block\b.*\bof the week\b", "prediction"),
]

# --- Running joke / meme detection ---
JOKE_PATTERNS = [
    (r"\btaco\b", "Taco/Sacko references"),
    (r"\bsacko\b", "Sacko punishment talk"),
    (r"\bjailyard\b", "Jailyard league identity"),
    (r"\btank(ing|ed)?\b", "Tanking accusations"),
    (r"\bcollusion\b", "Collusion accusations"),
    (r"\bveto\b", "Trade veto drama"),
    (r"\bcommish\b", "Commissioner authority"),
    (r"\bL\b(?=[\s!.])", "Taking Ls"),
    (r"\bfraud\b", "Fraud label"),
    (r"\bcooked\b", "Cooked/done"),
    (r"\bdead\b.*\b(team|roster|season)\b", "Season obituary"),
    (r"\bboom\b", "Boom game"),
    (r"\bbust\b", "Bust performance"),
]

# --- Trade-related patterns ---
TRADE_PATTERNS = [
    r"\btrade\b",
    r"\bsend(ing)?\b.*\bfor\b",
    r"\boffer\b",
    r"\bpackage\b.*\b(deal|trade)\b",
    r"\bwho says no\b",
    r"\bfleeced\b",
    r"\brobbery\b",
    r"\bsteal\b",
]


def get_hour(ts_str):
    """Extract hour from ISO timestamp."""
    dt = parse_ts(ts_str)
    return dt.hour if dt else None


def build_conversation_blocks(
    messages, max_gap_hours=2, context_before=2, context_after=1
):
    """Group messages into conversation blocks based on time gaps."""
    if not messages:
        return []
    blocks = []
    current_block = [0]  # indices into messages
    for i in range(1, len(messages)):
        ts_prev = parse_ts(messages[i - 1].get("timestamp_utc", ""))
        ts_curr = parse_ts(messages[i].get("timestamp_utc", ""))
        if ts_prev and ts_curr and (ts_curr - ts_prev) > timedelta(hours=max_gap_hours):
            blocks.append(current_block)
            current_block = [i]
        else:
            current_block.append(i)
    blocks.append(current_block)
    return blocks


def extract_notable_block(messages, target_idx, context_before=2, context_after=1):
    """Extract a conversational block around a target message."""
    start = max(0, target_idx - context_before)
    end = min(len(messages), target_idx + context_after + 1)
    # Truncate if time gap > 2 hours between any adjacent messages in block
    block_msgs = []
    for i in range(start, end):
        if block_msgs:
            prev_ts = parse_ts(messages[i - 1].get("timestamp_utc", ""))
            curr_ts = parse_ts(messages[i].get("timestamp_utc", ""))
            if prev_ts and curr_ts and (curr_ts - prev_ts) > timedelta(hours=2):
                if i <= target_idx:
                    block_msgs = []  # restart from here
                else:
                    break  # stop adding after
        msg = messages[i]
        block_msgs.append(
            {
                "sender": msg.get("sender") or "Unknown",
                "text": msg.get("text", "")
                or (f"[{msg.get('media', 'media')}]" if msg.get("media") else ""),
                "timestamp": msg.get("timestamp_utc", ""),
            }
        )
    return block_msgs


def compute_posting_stats(member_msgs):
    """Compute posting statistics for a member's messages."""
    if not member_msgs:
        return {
            "message_count": 0,
            "avg_length_chars": 0,
            "peak_hour": None,
            "emoji_heavy": False,
            "media_count": 0,
        }

    texts = [m.get("text", "") or "" for m in member_msgs]
    lengths = [len(t) for t in texts]
    hours = [get_hour(m.get("timestamp_utc", "")) for m in member_msgs]
    hours = [h for h in hours if h is not None]
    media_count = sum(1 for m in member_msgs if m.get("media"))

    # Emoji detection
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map
        "\U0001f1e0-\U0001f1ff"  # flags
        "\U00002702-\U000027b0"
        "\U000024c2-\U0001f251"
        "]+",
        flags=re.UNICODE,
    )
    emoji_msgs = sum(1 for t in texts if emoji_pattern.search(t))
    emoji_heavy = emoji_msgs > len(texts) * 0.2

    hour_counter = Counter(hours)
    peak_hour = hour_counter.most_common(1)[0][0] if hour_counter else None

    return {
        "message_count": len(member_msgs),
        "avg_length_chars": round(sum(lengths) / len(lengths)) if lengths else 0,
        "peak_hour": peak_hour,
        "emoji_heavy": emoji_heavy,
        "media_count": media_count,
    }


def detect_predictions(messages):
    """Find messages that look like predictions, bets, or hot takes."""
    predictions = []
    for i, msg in enumerate(messages):
        text = (msg.get("text", "") or "").lower()
        if len(text) < 10:
            continue
        for pattern, pred_type in PREDICTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                block = extract_notable_block(messages, i)
                predictions.append(
                    {
                        "author": msg.get("sender") or "Unknown",
                        "type": pred_type,
                        "quote_block": block,
                        "target_message_index": i,
                        "subject": (msg.get("text", "") or "")[:200],
                        "made_at": msg.get("timestamp_utc", ""),
                    }
                )
                break  # one match per message
    return predictions


def detect_relationship_interactions(messages, name_map):
    """Track who responds to whom based on adjacency patterns."""
    members = set(name_map.keys())
    # Also track system name "system" to ignore
    pair_counts = Counter()

    for i in range(1, len(messages)):
        sender = messages[i].get("sender") or ""
        prev_sender = messages[i - 1].get("sender") or ""
        if not sender or not prev_sender or sender == prev_sender:
            continue
        if sender not in members or prev_sender not in members:
            continue
        # Check time gap
        ts_prev = parse_ts(messages[i - 1].get("timestamp_utc", ""))
        ts_curr = parse_ts(messages[i].get("timestamp_utc", ""))
        if ts_prev and ts_curr and (ts_curr - ts_prev) > timedelta(hours=2):
            continue
        pair = tuple(sorted([sender, prev_sender]))
        pair_counts[pair] += 1

    # Build relationship interactions for top pairs
    interactions = []
    for pair, count in pair_counts.most_common(15):
        if count < 3:
            break
        # Find a notable exchange
        exchanges = []
        for i in range(1, len(messages)):
            s = messages[i].get("sender") or ""
            ps = messages[i - 1].get("sender") or ""
            if not s or not ps:
                continue
            if tuple(sorted([s, ps])) == pair:
                block = extract_notable_block(
                    messages, i, context_before=1, context_after=0
                )
                text = (messages[i].get("text", "") or "").lower()
                # Classify tone heuristically
                if any(w in text for w in ["lol", "lmao", "haha", "dead", "crying"]):
                    tone_hint = "comedic"
                elif any(
                    w in text for w in ["trash", "garbage", "worst", "fraud", "L "]
                ):
                    tone_hint = "competitive"
                else:
                    tone_hint = "neutral"
                exchanges.append(
                    {
                        "block": block,
                        "target_message_index": i,
                        "label": f"{pair[0]} and {pair[1]} exchange",
                        "tone_hint": tone_hint,
                    }
                )
                if len(exchanges) >= 3:
                    break

        # Determine overall tone from exchanges
        tone_hints = [e.get("tone_hint", "neutral") for e in exchanges]
        tone_counter = Counter(tone_hints)
        overall_tone = tone_counter.most_common(1)[0][0] if tone_counter else "neutral"

        interactions.append(
            {
                "pair": list(pair),
                "interaction_count": count,
                "tone": overall_tone,
                "notable_exchanges": [
                    {k: v for k, v in e.items() if k != "tone_hint"}
                    for e in exchanges[:2]
                ],
            }
        )

    return interactions


def detect_running_jokes(messages):
    """Find recurring phrases and joke patterns."""
    jokes = defaultdict(list)
    for i, msg in enumerate(messages):
        text = (msg.get("text", "") or "").lower()
        if len(text) < 3:
            continue
        for pattern, name in JOKE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                jokes[name].append(i)

    result = []
    for name, indices in sorted(jokes.items(), key=lambda x: -len(x[1])):
        if len(indices) < 2:
            continue
        result.append(
            {
                "name": name,
                "instances": [
                    {
                        "block": extract_notable_block(messages, idx),
                        "target_message_index": idx,
                    }
                    for idx in indices[:3]
                ],
                "frequency_this_month": len(indices),
            }
        )

    return result[:10]


def detect_consensus(messages, name_map):
    """Find group debates — topics where multiple people weigh in."""
    # Look for message clusters with 4+ unique senders within 20 messages
    members = set(name_map.keys())
    snapshots = []
    window = CONSENSUS_WINDOW_SIZE

    for start in range(0, len(messages) - window, window // 2):
        chunk = messages[start : start + window]
        senders = set(
            m.get("sender") or "" for m in chunk if (m.get("sender") or "") in members
        )
        if len(senders) >= CONSENSUS_MIN_SENDERS:
            # Find the most-mentioned topic keywords
            all_text = " ".join((m.get("text", "") or "").lower() for m in chunk)
            # Look for trade/player/strategy discussions
            is_trade = bool(re.search(r"\btrade\b", all_text))
            is_draft = bool(re.search(r"\bdraft\b", all_text))
            is_player = bool(
                re.search(r"\b(start|sit|pickup|waiver|add|drop)\b", all_text)
            )

            if is_trade or is_draft or is_player:
                topic = (
                    "trade discussion"
                    if is_trade
                    else "draft discussion" if is_draft else "roster moves"
                )
                # Find the message that sparked it
                mid = start + window // 2
                block = extract_notable_block(
                    messages, mid, context_before=2, context_after=2
                )
                snapshots.append(
                    {
                        "topic": topic,
                        "group_lean": f"{len(senders)} members engaged",
                        "dissenters": [],
                        "key_quotes": [{"block": block, "target_message_index": mid}],
                    }
                )
                if len(snapshots) >= 5:
                    break

    return snapshots


def find_greatest_moments(messages, name_map):
    """Find high-energy moments: long reply chains, lots of reactions, key phrases."""
    moments = []

    # Strategy: find messages followed by rapid bursts of activity
    for i in range(len(messages) - 3):
        # Check if 4+ messages follow within 5 minutes
        ts_start = parse_ts(messages[i].get("timestamp_utc", ""))
        if not ts_start:
            continue

        burst = 0
        for j in range(i + 1, min(i + 10, len(messages))):
            ts_j = parse_ts(messages[j].get("timestamp_utc", ""))
            if ts_j and (ts_j - ts_start) < timedelta(seconds=RAPID_BURST_SEC):
                burst += 1
            else:
                break

        if burst >= 4:
            text = messages[i].get("text", "") or ""
            if len(text) > 10:  # skip media-only triggers
                block = extract_notable_block(
                    messages, i, context_before=0, context_after=3
                )
                moments.append(
                    {
                        "title": f"{messages[i].get('sender', 'Someone')}'s moment",
                        "block": block,
                        "target_message_index": i,
                        "why_great": f"Triggered {burst} rapid responses within 5 minutes",
                        "burst_size": burst,
                    }
                )

    # Sort by burst size and take top 5
    moments.sort(key=lambda x: -x.get("burst_size", 0))
    return [{k: v for k, v in m.items() if k != "burst_size"} for m in moments[:5]]


def extract_lexicon(messages):
    """Find unique/unusual terms used repeatedly."""
    word_counts = Counter()
    for msg in messages:
        text = (msg.get("text", "") or "").lower()
        # Find words 4+ chars that aren't common English
        words = re.findall(r"\b[a-z]{4,}\b", text)
        word_counts.update(words)

    # Filter to interesting terms (not super common)
    COMMON = {
        "that",
        "this",
        "with",
        "from",
        "have",
        "they",
        "been",
        "would",
        "could",
        "will",
        "just",
        "like",
        "what",
        "when",
        "your",
        "about",
        "know",
        "think",
        "than",
        "more",
        "some",
        "into",
        "them",
        "then",
        "were",
        "said",
        "each",
        "much",
        "make",
        "made",
        "well",
        "back",
        "also",
        "good",
        "even",
        "here",
        "most",
        "want",
        "yeah",
        "need",
        "going",
        "really",
        "right",
        "still",
        "gonna",
        "getting",
        "pretty",
        "though",
        "should",
        "thing",
        "being",
        "doing",
        "their",
        "there",
        "these",
        "those",
        "which",
        "people",
        "after",
        "before",
        "never",
        "first",
        "other",
        "over",
        "only",
        "come",
        "very",
        "time",
        "look",
        "take",
        "down",
        "game",
        "team",
        "play",
        "player",
        "year",
        "week",
        "season",
        "pick",
        "draft",
        "trade",
        "point",
        "start",
        "last",
    }

    lexicon = {}
    for word, count in word_counts.most_common(50):
        if word not in COMMON and count >= 3 and len(word) >= 4:
            lexicon[word] = f"Used {count} times this month"
            if len(lexicon) >= 10:
                break

    return lexicon


def find_candidate_arcs(messages, predictions, relationships, name_map):
    """Identify narrative arcs from patterns in the data."""
    arcs = []
    members = set(name_map.keys())

    # Trade saga detection
    trade_msgs = [
        (i, m)
        for i, m in enumerate(messages)
        if any(re.search(p, (m.get("text", "") or "").lower()) for p in TRADE_PATTERNS)
    ]
    if len(trade_msgs) >= 3:
        # Cluster trade messages
        participants = sorted(
            set(m.get("sender") or "" for _, m in trade_msgs[:10]) & members
        )
        arcs.append(
            {
                "title": "Trade activity surge",
                "type": "trade_saga",
                "participants": participants[:5],
                "key_moments": [
                    {
                        "block": extract_notable_block(messages, idx),
                        "target_message_index": idx,
                        "significance": "Trade discussion",
                    }
                    for idx, _ in trade_msgs[:3]
                ],
                "status": "building" if len(trade_msgs) > 5 else "emerging",
            }
        )

    # Rivalry detection from relationships
    for rel in relationships[:3]:
        if rel.get("tone") in ("competitive", "hostile"):
            arcs.append(
                {
                    "title": f"{rel['pair'][0]} vs {rel['pair'][1]}",
                    "type": "rivalry",
                    "participants": rel["pair"],
                    "key_moments": [
                        {
                            "block": ex["block"],
                            "target_message_index": ex["target_message_index"],
                            "significance": ex["label"],
                        }
                        for ex in rel.get("notable_exchanges", [])[:2]
                    ],
                    "status": "building",
                }
            )

    # Prediction saga from predictions
    if len(predictions) >= 3:
        top_predictor = Counter(p["author"] for p in predictions).most_common(1)
        if top_predictor:
            name = top_predictor[0][0]
            arcs.append(
                {
                    "title": f"{name}'s hot take machine",
                    "type": "prediction_saga",
                    "participants": [name],
                    "key_moments": [
                        {
                            "block": p["quote_block"],
                            "target_message_index": p["target_message_index"],
                            "significance": p["subject"][:100],
                        }
                        for p in predictions
                        if p["author"] == name
                    ][:3],
                    "status": "building",
                }
            )

    return arcs[:8]


def process_month(month, chunk_path, name_map):
    """Process a single month's chunk into MAP output."""
    chunk = load_json(chunk_path)
    messages = chunk.get("messages", [])
    msg_count = len(messages)

    # Group messages by sender
    by_sender = defaultdict(list)
    for msg in messages:
        sender = msg.get("sender") or "Unknown"
        by_sender[sender].append(msg)

    # --- Persona observations ---
    persona_observations = []
    for member in name_map:
        member_msgs = by_sender.get(member, [])
        if not member_msgs:
            continue

        stats = compute_posting_stats(member_msgs)

        # Find notable quotes (longest messages, messages with many responses)
        sorted_by_len = sorted(
            [
                (i, m)
                for i, m in enumerate(messages)
                if m.get("sender") == member and len(m.get("text", "") or "") > 30
            ],
            key=lambda x: -len(x[1].get("text", "") or ""),
        )
        notable_quotes = []
        for idx, msg in sorted_by_len[:3]:
            block = extract_notable_block(messages, idx)
            notable_quotes.append(
                {
                    "block": block,
                    "target_message_index": idx,
                    "context": f"Notable message ({len(msg.get('text', '') or '')} chars)",
                }
            )

        # Observations
        observations = []
        if stats["message_count"] > msg_count * 0.15:
            observations.append(
                f"Dominant voice this month ({stats['message_count']} of {msg_count} messages)"
            )
        elif stats["message_count"] < msg_count * 0.03 and msg_count > 50:
            observations.append(f"Quiet month — only {stats['message_count']} messages")
        if stats["emoji_heavy"]:
            observations.append("Heavy emoji user this month")
        if stats["media_count"] > stats["message_count"] * 0.3:
            observations.append(
                f"Media-heavy poster ({stats['media_count']} media items)"
            )
        if stats["peak_hour"] is not None:
            if stats["peak_hour"] >= 22 or stats["peak_hour"] <= 4:
                observations.append(
                    f"Night owl — peak activity at {stats['peak_hour']}:00"
                )
        if stats["avg_length_chars"] > 150:
            observations.append(
                f"Essay writer — avg {stats['avg_length_chars']} chars per message"
            )
        elif stats["avg_length_chars"] < 30 and stats["message_count"] > 10:
            observations.append("One-liner specialist")

        persona_observations.append(
            {
                "member": member,
                "observations": (
                    observations
                    if observations
                    else [f"Active with {stats['message_count']} messages"]
                ),
                "notable_quotes": notable_quotes,
                "posting_stats": stats,
            }
        )

    # --- Other extractions ---
    predictions = detect_predictions(messages)
    relationships = detect_relationship_interactions(messages, name_map)
    running_jokes = detect_running_jokes(messages)
    consensus = detect_consensus(messages, name_map)
    greatest_moments = find_greatest_moments(messages, name_map)
    lexicon = extract_lexicon(messages)
    candidate_arcs = find_candidate_arcs(messages, predictions, relationships, name_map)

    return {
        "month": month,
        "message_count": msg_count,
        "persona_observations": persona_observations,
        "candidate_arcs": candidate_arcs,
        "relationship_interactions": relationships,
        "consensus_snapshots": consensus,
        "predictions_and_bets": predictions,
        "running_jokes": running_jokes,
        "greatest_moments": greatest_moments,
        "lexicon_candidates": lexicon,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Deterministic MAP phase for chat analysis"
    )
    parser.add_argument("--month", type=str, help="Process single month (YYYY-MM)")
    args = parser.parse_args()

    # Load name map
    name_map = load_json(NAME_MAP_PATH) if NAME_MAP_PATH.exists() else {}
    print(f"Name map: {len(name_map)} members")

    # Find raw chunk files
    raw_files = sorted(MAP_CACHE_DIR.glob("*_raw.json"))
    if not raw_files:
        print(f"ERROR: No raw chunk files in {MAP_CACHE_DIR}")
        print("  Run split_chat_months.py first")
        sys.exit(1)

    if args.month:
        raw_files = [f for f in raw_files if f.stem.replace("_raw", "") == args.month]
        if not raw_files:
            print(f"ERROR: No chunk file for month {args.month}")
            sys.exit(1)

    total = len(raw_files)
    success = 0
    for i, raw_path in enumerate(raw_files, 1):
        month = raw_path.stem.replace("_raw", "")
        out_path = MAP_CACHE_DIR / f"{month}.json"

        # Skip if already processed
        if out_path.exists():
            print(f"  [{i}/{total}] {month} -- cached")
            success += 1
            continue

        print(f"  [{i}/{total}] {month} -- processing...", end="", flush=True)
        try:
            result = process_month(month, raw_path, name_map)
            save_json(out_path, result)
            stats = result.get("persona_observations", [])
            preds = result.get("predictions_and_bets", [])
            arcs = result.get("candidate_arcs", [])
            print(
                f" {result['message_count']} msgs, {len(stats)} members, "
                f"{len(preds)} predictions, {len(arcs)} arcs"
            )
            success += 1
        except Exception as e:
            print(f" ERROR: {e}")

    print(f"\nDone. {success}/{total} months processed successfully.")


if __name__ == "__main__":
    main()
