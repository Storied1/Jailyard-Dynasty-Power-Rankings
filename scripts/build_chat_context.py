#!/usr/bin/env python
"""
Per-week relevancy engine: builds chat context for the AI column writer.

Takes parsed WhatsApp messages + Phase 2 analytics + week data and produces
a relevancy-scored chat context file that /write-week reads to inject real
group chat moments into the weekly column.

Usage:
    python scripts/build_chat_context.py --week 1 --season 2025
    python scripts/build_chat_context.py --week 1 --season 2025 --preseason
    python scripts/build_chat_context.py --week 1 --season 2025 --no-ai
    python scripts/build_chat_context.py --week 1 --season 2025 --verbose
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone

from shared import (
    CHAT_DIR,
    CONTENT_CHAT_DIR,
    DATA_DIR,
    PRESEASON_DIR,
    WEEKS_DIR,
    load_json,
    parse_ts,
)
from shared import save_json as _save_json

MEDIA_CATALOG_PATH = CONTENT_CHAT_DIR / "media-catalog.json"

# Standard NFL 2025: Week 1 games Sept 4-8, cutoff Tue Sept 9 06:59:59 UTC
WEEK1_CUTOFF_2025 = datetime(2025, 9, 9, 6, 59, 59, tzinfo=timezone.utc)
# Offseason starts roughly after Super Bowl — we use a wide window
PRESEASON_START_2025 = datetime(2025, 2, 10, 0, 0, 0, tzinfo=timezone.utc)
PRESEASON_END_2025 = datetime(2025, 9, 3, 23, 59, 59, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------


def save_json(path, data):
    """Write data as pretty JSON with UTF-8 (delegates to shared)."""
    _save_json(path, data, verbose=True)


# ---------------------------------------------------------------------------
# Temporal windowing
# ---------------------------------------------------------------------------


def compute_week_cutoff(week, season=2025):
    """
    Return (window_start_utc, cutoff_utc) for a given NFL week.

    Each week's cutoff is Tuesday 06:59:59 UTC after that week's MNF.
    Week 1 cutoff for 2025 = 2025-09-09 06:59:59 UTC.
    """
    if season == 2025:
        base = WEEK1_CUTOFF_2025
    else:
        # Approximate: Week 1 cutoff ≈ second Tuesday of September
        sept1 = datetime(season, 9, 1, 6, 59, 59, tzinfo=timezone.utc)
        days_to_tuesday = (1 - sept1.weekday()) % 7  # 1 = Tuesday
        if days_to_tuesday == 0:
            days_to_tuesday = 7
        # Second Tuesday
        base = sept1 + timedelta(days=days_to_tuesday + 7)

    cutoff = base + timedelta(weeks=(week - 1))
    window_start = cutoff - timedelta(weeks=1)
    return window_start, cutoff


def compute_preseason_window(season=2025):
    """Return (start, end) for preseason messages."""
    if season == 2025:
        return PRESEASON_START_2025, PRESEASON_END_2025
    start = datetime(season, 2, 10, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(season, 9, 3, 23, 59, 59, tzinfo=timezone.utc)
    return start, end


def filter_messages_in_window(messages, window_start, window_end):
    """Return messages whose timestamp_utc falls within [start, end]."""
    result = []
    for msg in messages:
        ts = parse_ts(msg.get("timestamp_utc"))
        if ts is None:
            continue
        if window_start <= ts <= window_end:
            result.append(msg)
    return result


# ---------------------------------------------------------------------------
# Identity resolution
# ---------------------------------------------------------------------------


def build_identity_maps(identity_chain):
    """
    From identity_chain.json, build:
      - roster_to_names: {roster_id -> [whatsapp names]}
      - name_to_roster: {whatsapp_name_lower -> roster_id}
      - roster_to_team: {roster_id -> team_name}
    """
    roster_to_names = {}
    name_to_roster = {}
    roster_to_team = {}

    # Handle the actual identity_chain.json format from parse_whatsapp.py:
    # {"by_roster_id": {"1": {"whatsapp_name": "...", "team_name": "...", ...}}, "by_whatsapp": {...}, ...}
    if isinstance(identity_chain, dict) and "by_roster_id" in identity_chain:
        for rid_str, info in identity_chain["by_roster_id"].items():
            rid = int(rid_str)
            wa_name = info.get("whatsapp_name", "")
            team = info.get("team_name", "")
            roster_to_team[rid] = team
            if wa_name:
                roster_to_names[rid] = [wa_name]
                name_to_roster[wa_name.lower()] = rid
    else:
        # Fallback: list or dict with "identities"/"entries" key
        entries = (
            identity_chain
            if isinstance(identity_chain, list)
            else identity_chain.get("identities", identity_chain.get("entries", []))
        )
        for entry in entries:
            rid = entry.get("roster_id")
            if rid is None:
                continue
            whatsapp_names = entry.get("whatsapp_names", [])
            team_name = entry.get("team_name", "")
            roster_to_names[rid] = whatsapp_names
            roster_to_team[rid] = team_name
            for name in whatsapp_names:
                name_to_roster[name.lower()] = rid

    return roster_to_names, name_to_roster, roster_to_team


def resolve_sender(sender, name_to_roster, roster_to_team):
    """Given a WhatsApp sender name, return (roster_id, team_name) or (None, None)."""
    if not sender:
        return None, None  # system messages / parser mis-splits have sender=None
    key = sender.strip().lower()
    rid = name_to_roster.get(key)
    if rid is None:
        return None, None
    return rid, roster_to_team.get(rid, "")


# ---------------------------------------------------------------------------
# Week data helpers
# ---------------------------------------------------------------------------


def get_matchup_roster_pairs(week_data):
    """Return list of (roster_id_1, roster_id_2) from this week's matchups."""
    if not week_data:
        return []
    pairs = []
    for m in week_data.get("matchups", []):
        t1 = m.get("team1", {}).get("roster_id")
        t2 = m.get("team2", {}).get("roster_id")
        if t1 is not None and t2 is not None:
            pairs.append((t1, t2))
    return pairs


def get_week_high_low_scorers(week_data):
    """Return (high_scorer_roster_id, low_scorer_roster_id) for the week."""
    if not week_data:
        return None, None
    scores = []
    for m in week_data.get("matchups", []):
        for side in ("team1", "team2"):
            team = m.get(side, {})
            rid = team.get("roster_id")
            pts = team.get("points", 0)
            if rid is not None:
                scores.append((rid, pts))
    if not scores:
        return None, None
    scores.sort(key=lambda x: x[1])
    return scores[-1][0], scores[0][0]


def get_all_player_names(week_data):
    """Return set of player names mentioned in matchups (top_scorers)."""
    if not week_data:
        return set()
    names = set()
    for m in week_data.get("matchups", []):
        for side in ("team1", "team2"):
            for p in m.get(side, {}).get("top_scorers", []):
                names.add(p.get("name", "").lower())
    return names


def get_all_team_names(week_data, roster_to_team=None):
    """Return set of team names from matchups. Falls back to the full
    league roster when week_data is absent -- preseason has no per-week
    matchups, but all teams are still in scope for keyword matching."""
    names = set()
    if week_data:
        for m in week_data.get("matchups", []):
            for side in ("team1", "team2"):
                tn = m.get(side, {}).get("team_name", "")
                if tn:
                    names.add(tn.lower().strip())
    if not names and roster_to_team:
        names = {tn.lower().strip() for tn in roster_to_team.values() if tn}
    return names


# ---------------------------------------------------------------------------
# Conversational block extraction
# ---------------------------------------------------------------------------


def extract_block(messages, target_idx, context_before=2, context_after=1):
    """Extract a conversational block around a target message index."""
    start = max(0, target_idx - context_before)
    end = min(len(messages), target_idx + context_after + 1)

    target_ts = parse_ts(messages[target_idx].get("timestamp_utc"))
    block = []
    for i in range(start, end):
        msg = messages[i]
        msg_ts = parse_ts(msg.get("timestamp_utc"))
        # Truncate if gap > 2 hours from target
        if target_ts and msg_ts:
            gap = abs((msg_ts - target_ts).total_seconds())
            if gap > 7200:
                continue
        block.append(
            {
                "sender": msg.get("sender", ""),
                "text": msg.get("text", ""),
                "timestamp_local": msg.get(
                    "timestamp_local", msg.get("timestamp_utc", "")
                ),
            }
        )

    adjusted_target = target_idx - start
    # Adjust for any messages skipped due to time gap
    skipped_before = 0
    for i in range(start, min(target_idx, end)):
        msg_ts = parse_ts(messages[i].get("timestamp_utc"))
        if target_ts and msg_ts and abs((msg_ts - target_ts).total_seconds()) > 7200:
            skipped_before += 1
    adjusted_target -= skipped_before

    return {
        "block": block,
        "target_message_index": max(0, min(adjusted_target, len(block) - 1)),
    }


# ---------------------------------------------------------------------------
# Keyword matching
# ---------------------------------------------------------------------------


def build_keyword_index(
    week_data, identity_chain_data, roster_to_names, roster_to_team
):
    """
    Build a set of keywords/phrases to search for in chat messages:
    team names, owner names, player names, WhatsApp names.
    Returns dict: {keyword_lower: context_label}.
    """
    keywords = {}

    # Team names
    for tn in get_all_team_names(week_data, roster_to_team):
        keywords[tn] = f"team:{tn}"
        # Also add shortened forms (first word if multi-word)
        parts = tn.split()
        if len(parts) > 1:
            for p in parts:
                if len(p) > 3:
                    keywords[p.lower()] = f"team:{tn}"

    # Player names
    for pn in get_all_player_names(week_data):
        keywords[pn] = f"player:{pn}"
        # Last name only for common references
        parts = pn.split()
        if len(parts) > 1 and len(parts[-1]) > 3:
            keywords[parts[-1].lower()] = f"player:{pn}"

    # WhatsApp names and owner usernames
    for rid, names in roster_to_names.items():
        team = roster_to_team.get(rid, "")
        for n in names:
            keywords[n.lower()] = f"owner:{team}"

    return keywords


def message_mentions_keywords(msg_text, keywords):
    """Return list of matched keyword labels from message text."""
    text_lower = msg_text.lower()
    matches = []
    for kw, label in keywords.items():
        if kw in text_lower:
            matches.append(label)
    return matches


# ---------------------------------------------------------------------------
# Relevancy scoring
# ---------------------------------------------------------------------------

RELEVANCY_TYPES = [
    "prediction_aged_badly",
    "trash_talk",
    "bet_resolving",
    "rivalry_heat",
    "milestone_reaction",
    "hot_take",
    "callback_material",
]


def score_message_relevancy(
    msg,
    msg_idx,
    messages,
    week_data,
    matchup_pairs,
    name_to_roster,
    roster_to_team,
    keywords,
    high_scorer_rid,
    low_scorer_rid,
    relationships,
    media_catalog=None,
    verbose=False,
):
    """
    Score a single message for relevancy to this week.
    Returns (score, relevancy_type, why_relevant, suggested_use) or None.
    """
    text = msg.get("text", "")
    media = msg.get("media")
    msg_id = msg.get("id")

    # For media messages, also consider the catalog description as searchable text
    media_desc = ""
    if media and media_catalog and msg_id:
        catalog_entry = media_catalog.get(msg_id)
        if catalog_entry:
            media_desc = catalog_entry.get("description", "")

    # Allow media-only messages if they have a catalog description
    if (not text or len(text) < 10) and not media_desc:
        return None

    sender = msg.get("sender", "")
    sender_rid, sender_team = resolve_sender(sender, name_to_roster, roster_to_team)

    # Search both message text and media description for keywords
    searchable_text = text + (" " + media_desc if media_desc else "")
    kw_matches = message_mentions_keywords(searchable_text, keywords)
    if not kw_matches and sender_rid is None:
        return None

    score = 0.0
    rel_type = "callback_material"
    why = ""
    suggested = ""

    # --- Matchup-relevant: sender is in a matchup and mentions opponent ---
    matchup_opponent_rid = None
    if sender_rid is not None:
        for r1, r2 in matchup_pairs:
            if sender_rid == r1:
                matchup_opponent_rid = r2
                break
            if sender_rid == r2:
                matchup_opponent_rid = r1
                break

    mentions_opponent_team = False
    if matchup_opponent_rid is not None:
        opp_team = roster_to_team.get(matchup_opponent_rid, "").lower()
        if opp_team and opp_team in text.lower():
            mentions_opponent_team = True

    # Trash talk between opponents
    if matchup_opponent_rid is not None and mentions_opponent_team:
        score += 8.0
        rel_type = "trash_talk"
        opp_team_display = roster_to_team.get(matchup_opponent_rid, "opponent")
        why = f"{sender} talking about opponent {opp_team_display} before their matchup"
        suggested = "Power ranking blurb or Overheard in the Chat"

    # Hot take patterns
    hot_take_patterns = [
        r"\b(washed|bust|overrated|underrated|sleeper|steal|flop)\b",
        r"\b(going to be|will be|gonna be|is the best|is the worst)\b",
        r"\b(bold prediction|hot take|unpopular opinion|mark my words)\b",
        r"\b(guaranteed|no chance|lock|easy win|no way)\b",
    ]
    hot_take_hits = sum(
        1 for p in hot_take_patterns if re.search(p, text, re.IGNORECASE)
    )
    if hot_take_hits >= 2:
        score += 5.0
        rel_type = "hot_take"
        why = why or f"{sender} dropped a hot take"
        suggested = suggested or "Essay color or Overheard in the Chat"
    elif hot_take_hits == 1:
        score += 2.0

    # Mentions a keyword-matched player or team
    player_mentions = [m for m in kw_matches if m.startswith("player:")]
    team_mentions = [m for m in kw_matches if m.startswith("team:")]
    owner_mentions = [m for m in kw_matches if m.startswith("owner:")]

    if player_mentions:
        score += 2.0
        why = why or f"{sender} mentioned {player_mentions[0].split(':')[1]}"
        suggested = suggested or "Power ranking blurb"
    if team_mentions:
        score += 1.5
    if owner_mentions:
        score += 1.0

    # Score modifiers
    if sender_rid is not None:
        if sender_rid == high_scorer_rid:
            score += 2.0
            why = why or f"{sender}'s team was the high scorer this week"
        if sender_rid == low_scorer_rid:
            score += 2.0
            why = why or f"{sender}'s team was the low scorer this week"

    # Multi-person thread bonus: check if nearby messages have different senders
    nearby_senders = set()
    for offset in range(-2, 3):
        ni = msg_idx + offset
        if 0 <= ni < len(messages):
            nearby_senders.add(messages[ni].get("sender", ""))
    if len(nearby_senders) >= 3:
        score += 1.0

    # Rivalry heat: check relationships graph
    if relationships and sender_rid is not None and matchup_opponent_rid is not None:
        rivalry_pairs = relationships.get("rivalries", [])
        for riv in rivalry_pairs:
            riv_rids = {riv.get("roster_id_1"), riv.get("roster_id_2")}
            if sender_rid in riv_rids and matchup_opponent_rid in riv_rids:
                score += 3.0
                rel_type = "rivalry_heat"
                why = f"Rivalry matchup: {sender} vs their rival"
                break

    # Media relevancy boost: described media mentioning players/teams
    if media_desc:
        media_kw_matches = message_mentions_keywords(media_desc, keywords)
        if media_kw_matches:
            score += 3.0
            rel_type = rel_type or "media_relevant"
            why = (
                why
                or f"{sender} shared media about {media_kw_matches[0].split(':')[1]}"
            )
            suggested = suggested or "Visual in Power ranking blurb"

    # Penalty: very short or unclear messages
    if len(text) < 20 and not media_desc:
        score -= 1.0
    # Penalty: media-only messages without catalog description
    if (
        text.startswith("<Media omitted>") or text.startswith("image omitted")
    ) and not media_desc:
        score -= 3.0

    if score < 2.0:
        return None

    return (
        round(score, 1),
        rel_type,
        why or f"Keyword match from {sender}",
        suggested or "Overheard in the Chat",
    )


# ---------------------------------------------------------------------------
# Arc matching
# ---------------------------------------------------------------------------


def _month_le(month_str, cutoff_dt):
    """True if a 'YYYY-MM' month string is on/before the cutoff datetime.

    Arc spans and key-moment dates are month-grained; the as-if-realtime
    boundary only needs month resolution for them. None == not-future (True).
    """
    if not month_str:
        return True
    return str(month_str)[:7] <= cutoff_dt.strftime("%Y-%m")


def find_active_arcs(
    arcs, week, season, week_data, roster_to_team, cutoff, name_to_roster=None
):
    """Find arcs relevant to this week and annotate with weekly development."""
    if not arcs:
        return []

    active = []
    arc_list = arcs if isinstance(arcs, list) else arcs.get("arcs", [])

    # Get roster_ids playing this week. Preseason (week_data=None): there's
    # no matchup slate yet, so every team in the league is in scope.
    if week_data:
        playing_rids = set()
        for m in week_data.get("matchups", []):
            playing_rids.add(m.get("team1", {}).get("roster_id"))
            playing_rids.add(m.get("team2", {}).get("roster_id"))
    else:
        playing_rids = set(roster_to_team.keys())

    for arc in arc_list:
        span = arc.get("span", {}) if isinstance(arc.get("span"), dict) else {}
        start = span.get("start") or arc.get("started")
        # As-of-week-N: an arc that starts AFTER the cutoff is the future.
        # Do NOT filter on the baked season-end status -- an arc that resolves
        # later was still live earlier and must appear in those weeks.
        if not _month_le(start, cutoff):
            continue
        end = span.get("end")
        as_of_status = "resolved" if (end and _month_le(end, cutoff)) else "active"

        # Check if any arc participants are playing this week
        participants = arc.get("roster_ids", arc.get("participants", []))
        if isinstance(participants, list):
            participant_rids = set()
            for p in participants:
                if isinstance(p, int):
                    participant_rids.add(p)
                elif isinstance(p, dict):
                    participant_rids.add(p.get("roster_id"))
                elif isinstance(p, str) and name_to_roster:
                    # arcs.json stores WhatsApp display names -- resolve them
                    rid = name_to_roster.get(p.strip().lower())
                    if rid is not None:
                        participant_rids.add(rid)
        else:
            participant_rids = set()

        overlap = participant_rids & playing_rids
        if not overlap:
            continue

        # Build development note from matchup results (preseason: no
        # matchups exist yet, so there's nothing to report developing).
        developments = []
        if week_data:
            for m in week_data.get("matchups", []):
                t1_rid = m.get("team1", {}).get("roster_id")
                t2_rid = m.get("team2", {}).get("roster_id")
                if t1_rid in participant_rids or t2_rid in participant_rids:
                    winner = m.get("winner", "")
                    margin = m.get("margin", 0)
                    developments.append(f"{winner} won by {margin}")

        if developments:
            development_note = "; ".join(developments)
        elif not week_data:
            development_note = f"Entering the {season} season"
        else:
            development_note = "Participants active this week"

        active.append(
            {
                "arc_id": arc.get("arc_id", arc.get("id", "")),
                "title": arc.get("title", ""),
                "status": as_of_status,
                "this_week_development": development_note,
                "suggested_framing": arc.get(
                    "suggested_framing",
                    arc.get("framing", "Continue tracking this arc"),
                ),
            }
        )

    return active


# ---------------------------------------------------------------------------
# Prediction resolution
# ---------------------------------------------------------------------------


def resolve_predictions(predictions, week, season, week_data, cutoff):
    """
    Check predictions that can be resolved given this week's results.
    Returns list of resolved prediction objects.
    """
    if not predictions:
        return []
    if not week_data:
        return []  # nothing to resolve against pre-week-1

    resolved = []
    pred_list = (
        predictions
        if isinstance(predictions, list)
        else predictions.get("predictions", [])
    )

    # Build a lookup of team results this week
    team_results = {}
    for m in week_data.get("matchups", []):
        for side in ("team1", "team2"):
            t = m.get(side, {})
            tn = t.get("team_name", "").strip()
            pts = t.get("points", 0)
            won = m.get("winner", "").strip() == tn
            team_results[tn.lower()] = {"points": pts, "won": won, "team_name": tn}

    # Build player point lookup
    player_scores = {}
    for m in week_data.get("matchups", []):
        for side in ("team1", "team2"):
            for p in m.get(side, {}).get("top_scorers", []):
                player_scores[p.get("name", "").lower()] = p.get("points", 0)

    for pred in pred_list:
        made_at = pred.get("made_at")
        if made_at:
            try:
                if parse_ts(made_at) > cutoff:
                    continue  # prediction not yet made as of week N
            except (ValueError, TypeError):
                pass
        status = pred.get("status", "open")
        if status != "open":
            continue

        # Check if prediction's resolve_by week has arrived
        resolve_week = pred.get("resolve_by_week")
        resolve_season = pred.get("resolve_by_season", season)
        if resolve_week and resolve_season == season and resolve_week <= week:
            pass  # Eligible for resolution
        elif not resolve_week:
            pass  # No explicit deadline, try to resolve
        else:
            continue

        quote = pred.get("quote", pred.get("text", ""))
        author = pred.get("author", "")
        resolution = None
        evidence = ""
        comedic_value = 5

        # Try to match player names in prediction text
        quote_lower = quote.lower()
        for pname, pts in player_scores.items():
            if pname in quote_lower:
                # Check sentiment of prediction
                neg_words = [
                    "washed",
                    "bust",
                    "done",
                    "trash",
                    "bad",
                    "terrible",
                    "won't",
                    "can't",
                ]
                pos_words = [
                    "elite",
                    "best",
                    "top",
                    "mvp",
                    "fire",
                    "stud",
                    "league winner",
                    "going off",
                ]
                is_negative = any(w in quote_lower for w in neg_words)
                is_positive = any(w in quote_lower for w in pos_words)

                if is_negative and pts > 20:
                    resolution = "wrong"
                    evidence = f"{pname.title()} scored {pts} in Week {week}"
                    comedic_value = 9
                elif is_positive and pts < 5:
                    resolution = "wrong"
                    evidence = f"{pname.title()} scored only {pts} in Week {week}"
                    comedic_value = 8
                elif is_positive and pts > 20:
                    resolution = "right"
                    evidence = f"{pname.title()} scored {pts} in Week {week}"
                    comedic_value = 4
                elif is_negative and pts < 5:
                    resolution = "right"
                    evidence = f"{pname.title()} scored only {pts} in Week {week}"
                    comedic_value = 3
                break

        # Try team-level resolution
        if resolution is None:
            for tname_lower, result in team_results.items():
                if tname_lower in quote_lower or any(
                    w in quote_lower for w in tname_lower.split() if len(w) > 3
                ):
                    neg_words = [
                        "trash",
                        "terrible",
                        "worst",
                        "bottom",
                        "last",
                        "no chance",
                    ]
                    pos_words = [
                        "championship",
                        "best",
                        "top",
                        "title",
                        "gonna win",
                        "easy",
                    ]
                    is_negative = any(w in quote_lower for w in neg_words)
                    is_positive = any(w in quote_lower for w in pos_words)

                    if is_negative and result["won"]:
                        resolution = "aging_badly"
                        evidence = f"{result['team_name']} won in Week {week} ({result['points']} pts)"
                        comedic_value = 7
                    elif is_positive and not result["won"]:
                        resolution = "aging_badly"
                        evidence = f"{result['team_name']} lost in Week {week} ({result['points']} pts)"
                        comedic_value = 7
                    break

        if resolution:
            resolved.append(
                {
                    "prediction_id": pred.get("prediction_id", pred.get("id", "")),
                    "author": author,
                    "original_quote": quote,
                    "made_at_local": pred.get(
                        "timestamp_local", pred.get("made_at", "")
                    ),
                    "resolution": resolution,
                    "evidence": evidence,
                    "comedic_value": comedic_value,
                }
            )

    return resolved


# ---------------------------------------------------------------------------
# Sentiment snapshot
# ---------------------------------------------------------------------------


def build_sentiment_snapshot(
    window_messages, name_to_roster, roster_to_team, week_data
):
    """
    Build per-owner sentiment snapshot: activity level, mood, notable behavior.
    """
    # Count messages per roster_id
    counts = {}
    texts = {}
    for msg in window_messages:
        sender = msg.get("sender", "")
        rid, team = resolve_sender(sender, name_to_roster, roster_to_team)
        if rid is None:
            continue
        counts[rid] = counts.get(rid, 0) + 1
        texts.setdefault(rid, []).append(msg.get("text", ""))

    # Determine who won/lost (preseason: no matchups yet, both stay empty --
    # the mood/activity heuristics below are still meaningful without them)
    winners = set()
    losers = set()
    if week_data:
        for m in week_data.get("matchups", []):
            winner_name = m.get("winner", "")
            for side in ("team1", "team2"):
                t = m.get(side, {})
                rid = t.get("roster_id")
                tn = t.get("team_name", "").strip()
                if tn == winner_name.strip():
                    winners.add(rid)
                else:
                    losers.add(rid)

    snapshot = {}

    for rid, team in roster_to_team.items():
        count = counts.get(rid, 0)
        msg_texts = texts.get(rid, [])

        # Activity level
        if count == 0:
            activity = "silent"
        elif count < 5:
            activity = "low"
        elif count < 15:
            activity = "medium"
        else:
            activity = "high"

        # Mood heuristic (simple keyword scan)
        all_text = " ".join(msg_texts).lower()
        mood = "neutral"
        hype_words = ["let's go", "lol", "haha", "fire", "W", "dub", "lfg"]
        salt_words = ["bs", "rigged", "trash", "unlucky", "smh", "pain"]
        cocky_words = ["easy", "too good", "can't lose", "goat", "best"]

        hype = sum(1 for w in hype_words if w.lower() in all_text)
        salt = sum(1 for w in salt_words if w.lower() in all_text)
        cocky = sum(1 for w in cocky_words if w.lower() in all_text)

        if cocky >= 2:
            mood = "cocky"
        elif hype >= 2:
            mood = "hyped"
        elif salt >= 2:
            mood = "salty"
        elif rid in losers and count < 3:
            mood = "silent"
        elif rid in winners and count > 5:
            mood = "cocky"

        # Notable behavior
        notable = ""
        if rid in winners and count > 10:
            notable = f"Posted {count} messages after the win"
        elif rid in losers and count == 0:
            notable = "Went completely silent after the loss"
        elif rid in losers and count < 3:
            notable = "Barely said a word after the loss"
        elif count > 15:
            notable = f"Most active chatter this week ({count} messages)"

        if team:
            snapshot[team] = {"activity": activity, "mood": mood, "notable": notable}

    return snapshot


# ---------------------------------------------------------------------------
# Chat highlights
# ---------------------------------------------------------------------------

HIGHLIGHT_CATEGORIES = ["reaction", "debate", "trash_talk", "celebration", "despair"]


def extract_chat_highlights(window_messages, scored_items, max_highlights=8):
    """
    Pull the top conversation blocks from the window, deduplicating with
    already-scored high/medium relevancy items.
    """
    # Collect message indices already used in scored items
    used_indices = set()
    for item in scored_items:
        # Mark a range around each used target
        ti = item.get("_source_idx")
        if ti is not None:
            for offset in range(-3, 4):
                used_indices.add(ti + offset)

    highlights = []

    # Simple heuristic: find multi-person exchanges
    i = 0
    while i < len(window_messages) and len(highlights) < max_highlights:
        if i in used_indices:
            i += 1
            continue

        # Look for clusters: 3+ messages within 5 minutes with 2+ senders
        cluster_end = i
        senders = {window_messages[i].get("sender", "")}
        base_ts = parse_ts(window_messages[i].get("timestamp_utc"))
        if base_ts is None:
            i += 1
            continue

        for j in range(i + 1, min(i + 10, len(window_messages))):
            msg_ts = parse_ts(window_messages[j].get("timestamp_utc"))
            if msg_ts is None:
                break
            if abs((msg_ts - base_ts).total_seconds()) > 300:
                break
            senders.add(window_messages[j].get("sender", ""))
            cluster_end = j

        if len(senders) >= 2 and (cluster_end - i) >= 2:
            # Found a conversation cluster
            block_data = extract_block(
                window_messages,
                (i + cluster_end) // 2,
                context_before=2,
                context_after=2,
            )

            # Classify
            combined_text = " ".join(
                m.get("text", "") for m in window_messages[i : cluster_end + 1]
            ).lower()
            category = "reaction"
            if any(
                w in combined_text for w in ["bet", "wager", "put money", "calling it"]
            ):
                category = "debate"
            elif any(
                w in combined_text for w in ["trash", "weak", "easy", "gonna destroy"]
            ):
                category = "trash_talk"
            elif any(w in combined_text for w in ["let's go", "lfg", "dub", "won"]):
                category = "celebration"
            elif any(w in combined_text for w in ["pain", "done", "worst", "kill me"]):
                category = "despair"

            # Build summary
            summary_parts = sorted(senders)[:3]
            summary = f"{', '.join(summary_parts)} exchanging messages"

            highlights.append(
                {
                    "block": block_data["block"],
                    "target_message_index": block_data["target_message_index"],
                    "category": category,
                    "summary": summary,
                }
            )

            # Skip past this cluster
            for idx in range(i, cluster_end + 1):
                used_indices.add(idx)
            i = cluster_end + 1
        else:
            i += 1

    return highlights


# ---------------------------------------------------------------------------
# Suggested callbacks
# ---------------------------------------------------------------------------


def sanitize_league_memory(league_memory, cutoff):
    """As-of-week-N league memory: timeless culture/lexicon + running jokes
    first seen on/before the cutoff. Excludes retrospective greatest_moments
    and the post-season meta block (both encode the ending)."""
    if not league_memory:
        return {}
    cutoff_month = cutoff.strftime("%Y-%m")
    jokes = []
    for j in league_memory.get("running_jokes", []):
        if not _month_le(j.get("first_seen"), cutoff):
            continue
        jk = dict(j)
        if jk.get("last_seen") and jk["last_seen"][:7] > cutoff_month:
            jk["last_seen"] = cutoff_month
            jk["still_active"] = True
        jokes.append(jk)
    return {
        "culture": league_memory.get("culture", {}),
        "lexicon": league_memory.get("lexicon", {}),
        "running_jokes": jokes,
    }


def build_suggested_callbacks(
    league_memory, arcs, predictions, week_data, roster_to_team, cutoff
):
    """Suggest callbacks to past events that connect to this week."""
    callbacks = []

    # From league memory: find entries that mention teams playing this week
    playing_teams = get_all_team_names(week_data, roster_to_team)

    if league_memory:
        entries = (
            league_memory
            if isinstance(league_memory, list)
            else league_memory.get("entries", league_memory.get("memories", []))
        )
        for entry in entries:
            text = json.dumps(entry).lower()
            for tn in playing_teams:
                if tn in text:
                    callbacks.append(
                        {
                            "source": "league-memory",
                            "content": entry.get(
                                "summary", entry.get("text", str(entry)[:120])
                            ),
                            "from_when": entry.get("date", entry.get("season", "")),
                            "connection_to_this_week": f"Involves {tn.title()}, who plays this week",
                        }
                    )
                    break
            if len(callbacks) >= 5:
                break

    # From arcs
    if arcs:
        arc_list = arcs if isinstance(arcs, list) else arcs.get("arcs", [])
        for arc in arc_list:
            span = arc.get("span", {}) if isinstance(arc.get("span"), dict) else {}
            if not _month_le(span.get("start") or arc.get("started"), cutoff):
                continue
            arc_text = json.dumps(arc).lower()
            for tn in playing_teams:
                if tn in arc_text:
                    callbacks.append(
                        {
                            "source": "arc",
                            "content": arc.get("title", ""),
                            "from_when": arc.get("started", arc.get("season", "")),
                            "connection_to_this_week": f"Active arc involving {tn.title()}",
                        }
                    )
                    break
            if len(callbacks) >= 8:
                break

    # From predictions (already aged)
    if predictions:
        pred_list = (
            predictions
            if isinstance(predictions, list)
            else predictions.get("predictions", [])
        )
        for pred in pred_list:
            made_at = pred.get("made_at")
            if made_at:
                try:
                    if parse_ts(made_at) > cutoff:
                        continue
                except (ValueError, TypeError):
                    pass
            if pred.get("status") == "open":
                quote = pred.get("quote", pred.get("text", "")).lower()
                for tn in playing_teams:
                    if tn in quote:
                        callbacks.append(
                            {
                                "source": "prediction",
                                "content": pred.get("quote", pred.get("text", "")),
                                "from_when": pred.get(
                                    "timestamp_local", pred.get("made_at", "")
                                ),
                                "connection_to_this_week": f"Open prediction about {tn.title()} — check if results confirm or deny",
                            }
                        )
                        break
            if len(callbacks) >= 10:
                break

    return callbacks[:10]


# ---------------------------------------------------------------------------
# AI-assisted scoring (optional)
# ---------------------------------------------------------------------------


def ai_rescore_candidates(candidates, week_data, api_key=None):
    """
    Optional: Use Claude Haiku to rescore candidate chat blocks.
    Only called when --no-ai is NOT set.
    """
    try:
        import anthropic
    except ImportError:
        print("  WARN: anthropic package not installed, skipping AI scoring")
        return candidates

    if not api_key:
        import os

        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  WARN: No ANTHROPIC_API_KEY, skipping AI scoring")
        return candidates

    # Batch candidates into groups of 10
    client = anthropic.Anthropic(api_key=api_key)
    batches = [candidates[i : i + 10] for i in range(0, len(candidates), 10)]

    rescored = []
    for batch in batches:
        prompt_items = []
        for idx, c in enumerate(batch):
            block_text = "\n".join(
                f"  {m['sender']}: {m['text']}" for m in c.get("block", [])
            )
            prompt_items.append(
                f"[{idx}] Score: {c.get('score', 0)} | Type: {c.get('type', '?')}\n"
                f"  Why: {c.get('why_relevant', '')}\n"
                f"  Chat:\n{block_text}"
            )

        prompt = (
            "You are scoring fantasy football group chat messages for a weekly column.\n"
            "Rate each on a 1-10 scale for: humor, relevancy to this week's matchups, "
            "and how well it would read in a Bill Simmons-style column.\n"
            'Return ONLY a JSON array of objects: [{"idx": 0, "score": 8.5, "type": "trash_talk", '
            '"why": "brief reason"}]\n\n' + "\n\n".join(prompt_items)
        )

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            # Extract JSON from response
            json_match = re.search(r"\[.*\]", text, re.DOTALL)
            if json_match:
                ai_scores = json.loads(json_match.group())
                for ai_item in ai_scores:
                    bidx = ai_item.get("idx", -1)
                    if 0 <= bidx < len(batch):
                        batch[bidx]["score"] = ai_item.get(
                            "score", batch[bidx].get("score", 0)
                        )
                        if ai_item.get("type"):
                            batch[bidx]["type"] = ai_item["type"]
                        if ai_item.get("why"):
                            batch[bidx]["why_relevant"] = ai_item["why"]
        except Exception as e:
            print(f"  WARN: AI scoring batch failed: {e}")

        rescored.extend(batch)

    return rescored


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_chat_context(
    week=None, season=2025, preseason=False, no_ai=False, verbose=False
):
    """Build the chat context JSON for a given week, or for preseason."""
    label = "Preseason" if preseason else f"Week {week}"
    print(f"\n=== Building chat context: {label}, Season {season} ===")
    if preseason:
        print("  Mode: PRESEASON")

    # --- Load all inputs ---
    messages = load_json(CHAT_DIR / "parsed_messages.json", "parsed_messages.json")
    identity_chain = load_json(CHAT_DIR / "identity_chain.json", "identity_chain.json")
    league_memory = load_json(
        CONTENT_CHAT_DIR / "league-memory.json", "league-memory.json"
    )
    arcs = load_json(CONTENT_CHAT_DIR / "arcs.json", "arcs.json")
    predictions = load_json(CONTENT_CHAT_DIR / "predictions.json", "predictions.json")
    relationships = load_json(
        CONTENT_CHAT_DIR / "relationships.json", "relationships.json"
    )
    load_json(CONTENT_CHAT_DIR / "consensus.json", "consensus.json")
    # Preseason has no week's matchup data yet -- week_data stays None.
    week_data = None
    if not preseason:
        week_data = load_json(
            WEEKS_DIR / f"week{week}_data.json", f"week{week}_data.json"
        )
    load_json(DATA_DIR / str(season) / "season_combined.json", "season_combined.json")

    # Validate required files
    if messages is None:
        print("ERROR: parsed_messages.json is required. Run parse_whatsapp.py first.")
        sys.exit(1)
    if identity_chain is None:
        print("ERROR: identity_chain.json is required. Run parse_whatsapp.py first.")
        sys.exit(1)
    if not preseason and week_data is None:
        print(
            f"ERROR: week{week}_data.json is required. Run extract_week_data.py --week {week} first."
        )
        sys.exit(1)

    # Normalize messages to a list
    if isinstance(messages, dict):
        messages = messages.get("messages", [])

    print(f"  Loaded {len(messages)} total messages")

    # --- Build identity maps ---
    roster_to_names, name_to_roster, roster_to_team = build_identity_maps(
        identity_chain
    )
    print(
        f"  Identity chain: {len(name_to_roster)} WhatsApp names -> {len(roster_to_team)} rosters"
    )

    # --- Compute temporal window ---
    if preseason:
        window_start, window_end = compute_preseason_window(season)
    else:
        window_start, window_end = compute_week_cutoff(week, season)

    print(f"  Window: {window_start.isoformat()} -> {window_end.isoformat()}")

    # --- Filter messages to window ---
    window_messages = filter_messages_in_window(messages, window_start, window_end)
    print(f"  Messages in window: {len(window_messages)}")

    # --- Week data helpers ---
    matchup_pairs = get_matchup_roster_pairs(week_data)
    high_scorer_rid, low_scorer_rid = get_week_high_low_scorers(week_data)
    keywords = build_keyword_index(
        week_data, identity_chain, roster_to_names, roster_to_team
    )

    if verbose:
        print(f"  Matchup pairs: {matchup_pairs}")
        print(
            f"  High scorer roster: {high_scorer_rid}, Low scorer roster: {low_scorer_rid}"
        )
        print(f"  Keywords indexed: {len(keywords)}")

    # --- Score every message in the window ---
    scored = []
    for idx, msg in enumerate(window_messages):
        result = score_message_relevancy(
            msg,
            idx,
            window_messages,
            week_data,
            matchup_pairs,
            name_to_roster,
            roster_to_team,
            keywords,
            high_scorer_rid,
            low_scorer_rid,
            relationships,
            verbose=verbose,
        )
        if result is None:
            continue

        score_val, rel_type, why, suggested = result
        block_data = extract_block(window_messages, idx)
        sender = msg.get("sender", "")
        sender_rid, sender_team = resolve_sender(sender, name_to_roster, roster_to_team)

        scored.append(
            {
                "type": rel_type,
                "block": block_data["block"],
                "target_message_index": block_data["target_message_index"],
                "author": sender,
                "author_team": sender_team,
                "author_roster_id": sender_rid,
                "why_relevant": why,
                "score": score_val,
                "suggested_use": suggested,
                "_source_idx": idx,  # internal, stripped before output
            }
        )

    print(f"  Scored candidates: {len(scored)}")

    # --- Optional AI rescoring ---
    if not no_ai and scored:
        print("  Running AI rescoring...")
        scored = ai_rescore_candidates(scored, week_data)

    # --- Split into high / medium ---
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Deduplicate: if two items share overlapping blocks, keep the higher-scored one
    deduped = []
    used_msg_ranges = set()
    for item in scored:
        source_idx = item.get("_source_idx", -1)
        item_range = frozenset(range(max(0, source_idx - 2), source_idx + 3))
        if item_range & used_msg_ranges:
            continue
        used_msg_ranges |= item_range
        deduped.append(item)

    high_relevancy = []
    medium_relevancy = []
    for item in deduped:
        # Strip internal field
        clean = {k: v for k, v in item.items() if not k.startswith("_")}
        if item["score"] >= 7.5:
            high_relevancy.append(clean)
        elif item["score"] >= 5.0:
            medium_relevancy.append(clean)

    # Cap at reasonable sizes
    high_relevancy = high_relevancy[:10]
    medium_relevancy = medium_relevancy[:15]

    print(f"  High relevancy: {len(high_relevancy)}")
    print(f"  Medium relevancy: {len(medium_relevancy)}")

    # --- Active arcs ---
    active_arcs = find_active_arcs(
        arcs,
        week,
        season,
        week_data,
        roster_to_team,
        window_end,
        name_to_roster=name_to_roster,
    )
    print(f"  Active arcs: {len(active_arcs)}")

    # --- Resolved predictions ---
    resolved_preds = resolve_predictions(
        predictions, week, season, week_data, window_end
    )
    print(f"  Resolved predictions: {len(resolved_preds)}")

    # --- Sentiment snapshot ---
    sentiment = build_sentiment_snapshot(
        window_messages, name_to_roster, roster_to_team, week_data
    )

    # --- Chat highlights ---
    all_scored_items = high_relevancy + medium_relevancy
    # Restore _source_idx temporarily for dedup in highlights
    for item in deduped:
        for hi in all_scored_items:
            if hi.get("block") == item.get("block"):
                hi["_source_idx"] = item.get("_source_idx")
    highlights = extract_chat_highlights(window_messages, all_scored_items)
    # Strip internal fields from highlights dedup items
    for hi in all_scored_items:
        hi.pop("_source_idx", None)
    print(f"  Chat highlights: {len(highlights)}")

    # --- Suggested callbacks ---
    callbacks = build_suggested_callbacks(
        league_memory, arcs, predictions, week_data, roster_to_team, window_end
    )
    print(f"  Suggested callbacks: {len(callbacks)}")

    # --- Assemble output ---
    total_context = len(high_relevancy) + len(medium_relevancy) + len(highlights)
    meta = {
        "type": "preseason" if preseason else "week",
        "season": season,
        "temporal_cutoff_utc": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_start_utc": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "messages_in_window": len(window_messages),
        "total_context_items": total_context,
    }
    if not preseason:
        meta["week"] = week
    output = {
        "meta": meta,
        "high_relevancy": high_relevancy,
        "medium_relevancy": medium_relevancy,
        "active_arcs_this_week": active_arcs,
        "resolved_predictions": resolved_preds,
        "sentiment_snapshot": sentiment,
        "league_memory": sanitize_league_memory(league_memory, window_end),
        "this_weeks_chat_highlights": highlights,
        "suggested_callbacks": callbacks,
    }

    # --- Write output ---
    if preseason:
        out_path = PRESEASON_DIR / "preseason_chat_context.json"
    else:
        out_path = WEEKS_DIR / f"week{week}_chat_context.json"
    save_json(out_path, output)

    print(f"\n  DONE: {total_context} context items for {label}")
    print(f"  Output: {out_path}")
    return output


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Build per-week chat context for the AI column writer."
    )
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help="NFL week number (1-18); required unless --preseason",
    )
    parser.add_argument(
        "--season", type=int, default=2025, help="Season year (default: 2025)"
    )
    parser.add_argument(
        "--preseason", action="store_true", help="Build preseason context window"
    )
    parser.add_argument(
        "--no-ai", action="store_true", help="Deterministic only, no Claude API calls"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print detailed scoring info"
    )

    args = parser.parse_args()

    if args.preseason:
        if args.week is not None:
            print(
                "ERROR: --week is not valid with --preseason (preseason has no week number)"
            )
            sys.exit(1)
    else:
        if args.week is None:
            print("ERROR: --week is required unless --preseason is set")
            sys.exit(1)
        if args.week < 1 or args.week > 18:
            print("ERROR: --week must be between 1 and 18")
            sys.exit(1)

    build_chat_context(
        week=args.week,
        season=args.season,
        preseason=args.preseason,
        no_ai=args.no_ai,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
