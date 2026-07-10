#!/usr/bin/env python
"""Deterministic REDUCE phase: merge MAP outputs into final analytics files.

Reads all content/chat/.map_cache/YYYY-MM.json MAP outputs and produces:
  content/chat/league-memory.json
  content/chat/arcs.json
  content/chat/predictions.json
  content/chat/relationships.json
  content/chat/consensus.json
  content/chat/personas/*.md

No AI calls — pure aggregation, ranking, and formatting.
"""

import sys
from collections import Counter, defaultdict
from datetime import datetime

from shared import CONTENT_CHAT_DIR as CHAT_DIR
from shared import MAP_CACHE_DIR, NAME_MAP_PATH, REPO_ROOT, load_json
from shared import save_json as _save_json

FINGERPRINTS_PATH = CHAT_DIR / "fingerprints.json"
PERSONAS_DIR = CHAT_DIR / "personas"


def save_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  Saved: {path.relative_to(REPO_ROOT)}")


def load_map_outputs():
    """Load all MAP phase outputs."""
    results = {}
    for path in sorted(MAP_CACHE_DIR.glob("*.json")):
        if path.stem.endswith("_raw"):
            continue
        results[path.stem] = load_json(path)
    return results


def reduce_league_memory(map_outputs, name_map, total_messages):
    """Produce league-memory.json from aggregated MAP data."""
    print("\n  Reducing: league-memory.json...")

    # Aggregate running jokes across months
    joke_counts = Counter()
    joke_instances = defaultdict(list)
    for month, data in map_outputs.items():
        for joke in data.get("running_jokes", []):
            name = joke.get("name", "")
            freq = joke.get("frequency_this_month", 0)
            joke_counts[name] += freq
            joke_instances[name].append(
                {
                    "month": month,
                    "frequency": freq,
                    "sample": joke.get("instances", [{}])[0].get("block", []),
                }
            )

    running_jokes = []
    for name, total in joke_counts.most_common(20):
        active_months = [inst["month"] for inst in joke_instances[name]]
        still_active = any(m >= "2025-09" for m in active_months)
        running_jokes.append(
            {
                "name": name,
                "total_frequency": total,
                "first_seen": min(active_months),
                "last_seen": max(active_months),
                "still_active": still_active,
                "sample_block": joke_instances[name][0].get("sample", []),
            }
        )

    # Aggregate greatest moments
    all_moments = []
    for month, data in map_outputs.items():
        for moment in data.get("greatest_moments", []):
            moment["month"] = month
            all_moments.append(moment)

    # Rank by how descriptive the "why_great" is (proxy for quality)
    greatest_moments = []
    for i, moment in enumerate(all_moments[:20], 1):
        greatest_moments.append(
            {
                "rank": i,
                "title": moment.get("title", "Untitled"),
                "block": moment.get("block", []),
                "target_message_index": moment.get("target_message_index", 0),
                "why_great": moment.get("why_great", ""),
                "month": moment.get("month", ""),
            }
        )

    # Aggregate lexicon
    all_lexicon = {}
    for month, data in map_outputs.items():
        for term, defn in data.get("lexicon_candidates", {}).items():
            if term in all_lexicon:
                all_lexicon[term] += f"; also {month}"
            else:
                all_lexicon[term] = defn

    # Monthly message counts for activity patterns
    total_days = len(map_outputs) * 30  # rough estimate
    avg_daily = total_messages / total_days if total_days else 0

    # Day of week from fingerprints
    peak_days = []
    if FINGERPRINTS_PATH.exists():
        fp = load_json(FINGERPRINTS_PATH)
        day_totals = Counter()
        for member, stats in fp.get("members", fp).items():
            for day, count in stats.get("timing", {}).get("day_of_week", {}).items():
                day_totals[day] += count
        peak_days = [d for d, _ in day_totals.most_common(3)]

    result = {
        "meta": {
            "generated": datetime.utcnow().isoformat() + "Z",
            "message_count": total_messages,
            "analysis_version": "1.0-deterministic",
            "months_analyzed": len(map_outputs),
        },
        "culture": {
            "summary": (
                "The Jailyard Dynasty group chat is a 12-member WhatsApp group that migrated "
                "from iMessage in September 2023. The chat peaks during NFL season months "
                "(September-January) with 1000-2400 messages per month, dropping to 38-180 "
                "in the deep offseason (May-June). The group's culture revolves around "
                "competitive trash talk, prediction receipts, trade debates, and a rich "
                "vocabulary of inside jokes. The tanking/Sacko discourse is the league's "
                "most enduring controversy."
            ),
            "communication_patterns": {
                "peak_activity_days": peak_days or ["Tue", "Sun", "Mon"],
                "peak_hours": ["16:00-22:00 PT"],
                "avg_daily_messages": round(avg_daily, 1),
                "media_vs_text_ratio": "~15% media",
            },
            "activity_triggers": [
                "Trade announcements",
                "Thursday Night Football",
                "Monday Night Football",
                "Draft day",
                "Playoff matchups",
                "Commissioner rulings",
                "Injury news",
            ],
        },
        "running_jokes": running_jokes,
        "greatest_moments": greatest_moments,
        "lexicon": all_lexicon,
    }
    _save_json(CHAT_DIR / "league-memory.json", result, verbose=True)
    return result


def reduce_arcs(map_outputs, name_map):
    """Produce arcs.json from candidate arcs across months."""
    print("\n  Reducing: arcs.json...")

    # Collect all candidate arcs
    all_arcs = []
    for month, data in map_outputs.items():
        for arc in data.get("candidate_arcs", []):
            arc["source_month"] = month
            all_arcs.append(arc)

    # Group by type and the FULL participant crew: same crew across months =
    # one ongoing saga; any-3-alphabetical over-merges (every month's trade
    # cluster shares the same alphabetical top-3, collapsing 20 arcs into 1).
    arc_groups = defaultdict(list)
    for arc in all_arcs:
        key = (arc.get("type", ""), tuple(sorted(arc.get("participants", []))))
        arc_groups[key].append(arc)

    # Merge groups into narrative arcs
    merged_arcs = []
    for (arc_type, participants), group in arc_groups.items():
        months = sorted(set(a.get("source_month", "") for a in group))
        all_moments = []
        for a in group:
            for km in a.get("key_moments", []):
                km["date"] = a.get("source_month", "")
                all_moments.append(km)

        # Determine status based on recency
        latest = max(months) if months else ""
        if latest >= "2025-09":
            status = "building"
        elif latest >= "2025-01":
            status = "cooling"
        else:
            status = "resolved"

        # Title from the most common arc title in the group
        titles = [a.get("title", "") for a in group]
        title = Counter(titles).most_common(1)[0][0] if titles else "Unnamed arc"

        slug = (
            f"{arc_type}-{'-'.join(p.lower().split()[0] for p in participants[:3])}-{months[0]}"
            if participants
            else f"{arc_type}-{months[0]}"
        )

        merged_arcs.append(
            {
                "arc_id": slug[:60],
                "title": title,
                "type": arc_type,
                "status": status,
                "span": {"start": months[0], "end": months[-1]} if months else {},
                "participants": list(participants),
                "key_moments": all_moments[:5],
                "narrative_potential": min(10, len(group) * 2 + len(all_moments)),
            }
        )

    # Sort by narrative potential
    merged_arcs.sort(key=lambda x: -x.get("narrative_potential", 0))
    _save_json(CHAT_DIR / "arcs.json", merged_arcs[:30], verbose=True)
    return merged_arcs[:30]


def reduce_predictions(map_outputs, name_map):
    """Produce predictions.json from all monthly predictions."""
    print("\n  Reducing: predictions.json...")

    all_preds = []
    for month, data in map_outputs.items():
        for pred in data.get("predictions_and_bets", []):
            pred["source_month"] = month
            all_preds.append(pred)

    # Deduplicate by author + subject similarity (rough)
    seen = set()
    unique_preds = []
    for pred in all_preds:
        key = (pred.get("author", ""), pred.get("subject", "")[:50])
        if key not in seen:
            seen.add(key)
            unique_preds.append(
                {
                    "id": f"pred-{len(unique_preds)+1:03d}",
                    "author_whatsapp": pred.get("author", ""),
                    "type": pred.get("type", "prediction"),
                    "quote_block": pred.get("quote_block", []),
                    "target_message_index": pred.get("target_message_index", 0),
                    "subject": pred.get("subject", ""),
                    "made_at": pred.get("made_at", ""),
                    "resolution": "pending",
                    "resolution_context": None,
                    "credibility_impact": 0,
                }
            )

    # Build credibility index
    cred_index = {}
    author_counts = Counter(p["author_whatsapp"] for p in unique_preds)
    for author, total in author_counts.items():
        cred_index[author] = {
            "total": total,
            "correct": 0,
            "wrong": 0,
            "pending": total,
            "accuracy_pct": None,
        }

    result = {
        "predictions": unique_preds,
        "credibility_index": cred_index,
    }
    _save_json(CHAT_DIR / "predictions.json", result, verbose=True)
    return result


def reduce_relationships(map_outputs, name_map):
    """Produce relationships.json from aggregated interaction data."""
    print("\n  Reducing: relationships.json...")

    pair_data = defaultdict(
        lambda: {"count": 0, "tones": [], "exchanges": [], "months": []}
    )

    for month, data in map_outputs.items():
        for rel in data.get("relationship_interactions", []):
            pair = tuple(sorted(rel.get("pair", [])))
            if len(pair) != 2:
                continue
            pair_data[pair]["count"] += rel.get("interaction_count", 0)
            pair_data[pair]["tones"].append(rel.get("tone", "neutral"))
            pair_data[pair]["months"].append(month)
            for ex in rel.get("notable_exchanges", []):
                pair_data[pair]["exchanges"].append(ex)

    pairs = []
    for pair, info in sorted(pair_data.items(), key=lambda x: -x[1]["count"]):
        # Determine overall tone
        tone_counter = Counter(info["tones"])
        overall_tone = tone_counter.most_common(1)[0][0] if tone_counter else "neutral"

        # Peak month
        month_counter = Counter(info["months"])
        peak_month = month_counter.most_common(1)[0][0] if month_counter else ""

        # Determine dynamic
        if overall_tone in ("hostile", "competitive"):
            dynamic = "rivalry"
        elif overall_tone == "comedic":
            dynamic = "comedic_duo"
        elif overall_tone == "friendly":
            dynamic = "alliance"
        else:
            dynamic = "frenemies" if info["count"] > 50 else "alliance"

        # Sentiment trajectory
        early_tones = [
            t for t, m in zip(info["tones"], info["months"]) if m < "2025-01"
        ]
        late_tones = [
            t for t, m in zip(info["tones"], info["months"]) if m >= "2025-01"
        ]
        if early_tones and late_tones:
            early_hostile = sum(
                1 for t in early_tones if t in ("hostile", "competitive")
            )
            late_hostile = sum(1 for t in late_tones if t in ("hostile", "competitive"))
            if late_hostile > early_hostile:
                trajectory = "cooling"
            elif late_hostile < early_hostile:
                trajectory = "warming"
            else:
                trajectory = "stable"
        else:
            trajectory = "stable"

        pairs.append(
            {
                "members": list(pair),
                "interaction_count": info["count"],
                "dynamic": dynamic,
                "sentiment_trajectory": trajectory,
                "peak_month": peak_month,
                "signature_moments": info["exchanges"][:3],
            }
        )

    result = {"pairs": pairs[:30]}
    _save_json(CHAT_DIR / "relationships.json", result, verbose=True)
    return result


def reduce_consensus(map_outputs, name_map):
    """Produce consensus.json from monthly consensus snapshots."""
    print("\n  Reducing: consensus.json...")

    all_snapshots = []
    for month, data in map_outputs.items():
        for snap in data.get("consensus_snapshots", []):
            snap["period"] = month
            all_snapshots.append(snap)

    # Group by topic type
    topic_groups = defaultdict(list)
    for snap in all_snapshots:
        topic_groups[snap.get("topic", "general")].append(snap)

    snapshots = []
    for topic, snaps in topic_groups.items():
        for snap in snaps[:3]:
            snapshots.append(
                {
                    "topic": snap.get("topic", topic),
                    "period": snap.get("period", ""),
                    "group_opinion": snap.get("group_lean", ""),
                    "dissenters": snap.get("dissenters", []),
                    "key_quotes": snap.get("key_quotes", []),
                    "resolution": "pending",
                }
            )

    result = {
        "snapshots": snapshots[:30],
        "collective_wrongs": [],
        "lone_wolves": [],
    }
    _save_json(CHAT_DIR / "consensus.json", result, verbose=True)
    return result


def reduce_personas(map_outputs, name_map):
    """Produce persona markdown files from aggregated observations."""
    print("\n  Reducing: persona profiles...")
    PERSONAS_DIR.mkdir(parents=True, exist_ok=True)

    # Load fingerprints
    fingerprints = {}
    if FINGERPRINTS_PATH.exists():
        fp_data = load_json(FINGERPRINTS_PATH)
        fingerprints = fp_data.get("members", fp_data)

    # Collect all persona observations by member
    member_data = defaultdict(list)
    for month, data in map_outputs.items():
        for obs in data.get("persona_observations", []):
            member = obs.get("member", "Unknown")
            member_data[member].append({"month": month, **obs})

    total = len(member_data)
    for i, (member, observations) in enumerate(sorted(member_data.items()), 1):
        identity = name_map.get(member, {})
        real_name = identity.get("real_name", member)
        team = identity.get("team_name", "Unknown")
        handle = identity.get("sleeper_handle", "N/A")
        display = identity.get("display_name", member)

        # Aggregate stats
        total_msgs = sum(
            o.get("posting_stats", {}).get("message_count", 0) for o in observations
        )
        active_months = len(
            [
                o
                for o in observations
                if o.get("posting_stats", {}).get("message_count", 0) > 0
            ]
        )

        # Collect all observations
        all_obs = []
        for o in observations:
            for note in o.get("observations", []):
                all_obs.append(f"- [{o.get('month', '')}] {note}")

        # Collect notable quotes
        all_quotes = []
        for o in observations:
            for q in o.get("notable_quotes", []):
                block = q.get("block", [])
                if block:
                    quote_text = block[0].get("text", "")[:100] if block else ""
                    all_quotes.append(f"- [{o.get('month', '')}] {quote_text}")

        # Fingerprint data
        fp = fingerprints.get(member, {})
        fp_section = ""
        if fp:
            vol = fp.get("volume", {})
            timing = fp.get("timing", {})
            style = fp.get("style", {})
            fp_section = f"""
## Communication DNA
- **Total messages**: {vol.get('total_messages', 'N/A')}
- **Avg length**: {vol.get('avg_length_chars', 'N/A')} chars ({vol.get('avg_length_words', 'N/A')} words)
- **Peak hour**: {timing.get('peak_hour', 'N/A')}:00
- **Late night %**: {timing.get('late_night_pct', 'N/A')}%
- **Top emojis**: {', '.join(e['emoji'] for e in style.get('emoji_top_10', [])[:5])}
- **Question %**: {style.get('question_pct', 'N/A')}%
- **CAPS %**: {style.get('caps_pct', 'N/A')}%
"""

        profile = f"""# {display} ({real_name})
**Team:** {team} | **Handle:** @{handle}

## Identity
- WhatsApp name: {member}
- Active in {active_months} of {len(map_outputs)} months analyzed
- Total messages in chat: {total_msgs}
{fp_section}
## Behavioral Observations
{chr(10).join(all_obs[:20]) if all_obs else '- No notable observations extracted'}

## Notable Quotes
{chr(10).join(all_quotes[:10]) if all_quotes else '- No notable quotes extracted'}

## Narrative Hooks
- Active storylines and callback opportunities to be enriched by AI pass
"""
        slug = member.lower().strip().replace(" ", "-").replace("~", "").strip("-")
        save_text(PERSONAS_DIR / f"{slug}.md", profile)

    print(f"  {total} persona profiles generated")


def main():
    print("=" * 60)
    print("  Jailyard Dynasty -- Chat REDUCE Phase (deterministic)")
    print("=" * 60)

    # Load MAP outputs
    map_outputs = load_map_outputs()
    if not map_outputs:
        print("ERROR: No MAP outputs found. Run map_chat_deterministic.py first.")
        sys.exit(1)
    print(f"  Loaded {len(map_outputs)} monthly analyses")

    # Load name map
    name_map = load_json(NAME_MAP_PATH) if NAME_MAP_PATH.exists() else {}
    print(f"  Name map: {len(name_map)} members")

    # Total messages
    total_messages = sum(d.get("message_count", 0) for d in map_outputs.values())
    print(f"  Total messages: {total_messages:,}")

    # Run all REDUCE operations
    reduce_league_memory(map_outputs, name_map, total_messages)
    reduce_arcs(map_outputs, name_map)
    reduce_predictions(map_outputs, name_map)
    reduce_relationships(map_outputs, name_map)
    reduce_consensus(map_outputs, name_map)
    reduce_personas(map_outputs, name_map)

    print("\n" + "=" * 60)
    print("  REDUCE phase complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
