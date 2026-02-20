#!/usr/bin/env python
"""Verify weekly content JSON against week data JSON.

Cross-references content/weeks/weekN_content.json against
content/weeks/weekN_data.json to catch data-accuracy errors
before they reach the rendered HTML.

Exit codes: 0 = PASS, 1 = FAIL, 2 = parse/file error
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEEKS_DIR = REPO_ROOT / "content" / "weeks"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_team(name: str) -> str:
    """Normalize team names for comparison.

    Handles: trailing spaces, Unicode hyphens (‑ vs -), case.
    """
    # Replace Unicode hyphens with ASCII hyphen
    name = unicodedata.normalize("NFKC", name)
    name = name.replace("\u2011", "-")  # non-breaking hyphen
    name = name.replace("\u2010", "-")  # hyphen
    name = name.replace("\u2013", "-")  # en-dash
    name = name.replace("\u2014", "-")  # em-dash
    return name.strip().lower()


def teams_match(a: str, b: str) -> bool:
    return normalize_team(a) == normalize_team(b)


def find_team_in_standings(team_name: str, standings: list[dict]) -> dict | None:
    for s in standings:
        if teams_match(s["team_name"], team_name):
            return s
    return None


def find_matchup_for_team(team_name: str, matchups: list[dict]) -> dict | None:
    for m in matchups:
        if teams_match(m["team1"]["team_name"], team_name) or \
           teams_match(m["team2"]["team_name"], team_name):
            return m
    return None


def get_team_side(team_name: str, matchup: dict) -> dict | None:
    if teams_match(matchup["team1"]["team_name"], team_name):
        return matchup["team1"]
    if teams_match(matchup["team2"]["team_name"], team_name):
        return matchup["team2"]
    return None


def movement_str_to_delta(movement: str) -> int | None:
    """Convert 'up_3' / 'down_1' / 'steady' to signed int."""
    if movement == "steady":
        return 0
    m = re.match(r"(up|down)_(\d+)", movement)
    if not m:
        return None
    val = int(m.group(2))
    return val if m.group(1) == "up" else -val


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"ERROR: Cannot load {path}: {e}")
        sys.exit(2)


def load_prev_content(week: int) -> dict | None:
    """Load previous week's content JSON if it exists."""
    path = WEEKS_DIR / f"week{week}_content.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


# ---------------------------------------------------------------------------
# Tier 1: Structural checks
# ---------------------------------------------------------------------------

def check_rankings_completeness(content: dict, data: dict, errors: list):
    """All 12 teams present, ranks 1-12 sequential."""
    rankings = content.get("rankings", [])
    if len(rankings) != 12:
        errors.append(f"Rankings has {len(rankings)} entries, expected 12")
        return

    ranks = sorted(r["rank"] for r in rankings)
    if ranks != list(range(1, 13)):
        errors.append(f"Ranks are not sequential 1-12: {ranks}")


def check_rankings_match_standings(content: dict, data: dict, errors: list):
    """Each ranking entry matches corresponding standings entry."""
    standings = data.get("standings", [])
    standings_by_rank = {s["rank"]: s for s in standings}

    for r in content.get("rankings", []):
        rank = r["rank"]
        s = standings_by_rank.get(rank)
        if not s:
            errors.append(f"Rank {rank}: no matching standings entry")
            continue

        # Check fields (skip prev_rank if null — week 1)
        for field in ["prev_rank", "record", "owner"]:
            data_val = s.get(field)
            content_val = r.get(field)
            if data_val is None:
                continue  # No data to compare against (e.g. week 1 prev_rank)
            if content_val != data_val:
                errors.append(
                    f"Rank {rank} ({r.get('team_name', '?')}): "
                    f"{field} is '{content_val}' but data says '{data_val}'"
                )

        # Team name (normalized comparison)
        if not teams_match(r.get("team_name", ""), s.get("team_name", "")):
            errors.append(
                f"Rank {rank}: team_name is '{r.get('team_name')}' "
                f"but data says '{s.get('team_name')}'"
            )


def check_movement(content: dict, data: dict, errors: list):
    """Movement string matches computed prev_rank - rank delta."""
    standings = data.get("standings", [])
    standings_by_rank = {s["rank"]: s for s in standings}

    for r in content.get("rankings", []):
        rank = r["rank"]
        s = standings_by_rank.get(rank)
        if not s:
            continue

        prev_rank = s.get("prev_rank")
        if prev_rank is None:
            # Week 1: no previous rank, skip movement check
            continue

        expected_delta = prev_rank - rank
        actual_delta = movement_str_to_delta(r.get("movement", ""))
        if actual_delta is None:
            errors.append(
                f"Rank {rank} ({r.get('team_name', '?')}): "
                f"invalid movement string '{r.get('movement')}'"
            )
        elif actual_delta != expected_delta:
            errors.append(
                f"Rank {rank} ({r.get('team_name', '?')}): "
                f"movement is '{r.get('movement')}' (delta={actual_delta}) "
                f"but prev_rank={prev_rank} → rank={rank} "
                f"= delta {expected_delta}"
            )


def check_confessional_teams(content: dict, data: dict, errors: list):
    """All confessional team_names exist in standings."""
    standings_names = {normalize_team(s["team_name"]) for s in data.get("standings", [])}

    for c in content.get("confessionals", []):
        if normalize_team(c.get("team_name", "")) not in standings_names:
            errors.append(
                f"Confessional team_name '{c.get('team_name')}' "
                f"not found in standings"
            )


def check_picks_matchups(content: dict, data: dict, errors: list):
    """Picks home/away match next_matchups; pick is home or away."""
    next_matchups = data.get("next_matchups", [])
    if not next_matchups:
        return  # Last week of season has no next matchups

    # Build set of (normalized_team1, normalized_team2) from next_matchups
    nm_pairs = set()
    for nm in next_matchups:
        pair = tuple(sorted([normalize_team(nm["team1"]), normalize_team(nm["team2"])]))
        nm_pairs.add(pair)

    for p in content.get("picks", []):
        home = p.get("home", "")
        away = p.get("away", "")
        pair = tuple(sorted([normalize_team(home), normalize_team(away)]))

        if pair not in nm_pairs:
            errors.append(
                f"Pick matchup '{home}' vs '{away}' "
                f"not found in next_matchups"
            )

        pick = p.get("pick", "")
        if not teams_match(pick, home) and not teams_match(pick, away):
            errors.append(
                f"Pick '{pick}' is neither home ('{home}') "
                f"nor away ('{away}')"
            )


def check_media_slots(content: dict, data: dict, errors: list):
    """Every {{media:slot_id}} token has a matching media_slots entry."""
    slots = {s["slot_id"] for s in content.get("media_slots", [])}

    # Collect all text fields to scan for tokens
    texts = []
    texts.append(content.get("essay", ""))
    for r in content.get("rankings", []):
        texts.append(r.get("blurb", ""))
    for c in content.get("confessionals", []):
        texts.append(c.get("text", ""))
    for m in content.get("mailbag", []):
        texts.append(m.get("answer", ""))
        texts.append(m.get("question", ""))
    for b in content.get("bits", []):
        texts.append(b.get("text", ""))
    for p in content.get("picks", []):
        texts.append(p.get("blurb", ""))

    all_text = "\n".join(texts)
    tokens = set(re.findall(r"\{\{media:([\w-]+)\}\}", all_text))

    for token in tokens:
        if token not in slots:
            errors.append(
                f"Media token '{{{{media:{token}}}}}' found in text "
                f"but no matching media_slots entry"
            )

    for slot_id in slots:
        if slot_id not in tokens:
            errors.append(
                f"media_slots entry '{slot_id}' exists "
                f"but no {{{{media:{slot_id}}}}} token found in text"
            )


def check_picks_ledger(content: dict, data: dict, errors: list):
    """Picks ledger cumulative_record math is correct."""
    meta = content.get("meta", {})
    ledger = meta.get("picks_ledger", {})
    if not ledger:
        return  # Week 1 has no ledger

    week = meta.get("week", 0)

    # Sum all straight_up records from this content AND prior weeks' ledgers
    total_w, total_l = 0, 0

    # Current ledger entries
    for key, result in ledger.items():
        if not isinstance(result, dict):
            continue
        record_str = result.get("straight_up", "")
        m = re.match(r"(\d+)-(\d+)", record_str)
        if m:
            total_w += int(m.group(1))
            total_l += int(m.group(2))

    # Load prior weeks' ledgers
    for prev_week in range(2, week):
        prev_content = load_prev_content(prev_week)
        if prev_content:
            prev_ledger = prev_content.get("meta", {}).get("picks_ledger", {})
            for key, result in prev_ledger.items():
                if not isinstance(result, dict):
                    continue
                record_str = result.get("straight_up", "")
                m = re.match(r"(\d+)-(\d+)", record_str)
                if m:
                    total_w += int(m.group(1))
                    total_l += int(m.group(2))

    # Find cumulative record in the most recent ledger entry
    cum_record = ""
    for key, result in ledger.items():
        if isinstance(result, dict) and "cumulative_record" in result:
            cum_record = result["cumulative_record"]

    if cum_record:
        m = re.match(r"(\d+)-(\d+)", cum_record)
        if m:
            expected_w, expected_l = int(m.group(1)), int(m.group(2))
            if total_w != expected_w or total_l != expected_l:
                errors.append(
                    f"Picks ledger cumulative_record is '{cum_record}' "
                    f"but sum of all straight_up records is {total_w}-{total_l}"
                )


def run_tier1(content: dict, data: dict) -> dict:
    """Run all Tier 1 structural checks."""
    checks = [
        ("rankings_completeness", check_rankings_completeness),
        ("rankings_match_standings", check_rankings_match_standings),
        ("movement_strings", check_movement),
        ("confessional_teams", check_confessional_teams),
        ("picks_matchups", check_picks_matchups),
        ("media_slots", check_media_slots),
        ("picks_ledger", check_picks_ledger),
    ]

    all_errors = []
    passed = 0
    failed = 0

    for name, fn in checks:
        errs = []
        fn(content, data, errs)
        if errs:
            failed += 1
            all_errors.extend(errs)
        else:
            passed += 1

    return {"passed": passed, "failed": failed, "errors": all_errors}


# ---------------------------------------------------------------------------
# Tier 2: Content cross-reference (regex extraction)
# ---------------------------------------------------------------------------

def extract_player_score_claims(text: str) -> list[tuple[str, float]]:
    """Extract 'Player XX.X' score claims from text.

    Patterns matched:
    - "Player's 31.3" / "Player's 31.3-point"
    - "Player added 19.0" / "scored 19.0" / "contributed 19.0"
    - "Player dropped 25.0" / "erupted for 25.0" / "posted 18.1"
    - "Player (16.0)" / "Player at 16.0"
    - "Player went off for 25.0"
    - "Player chipped in 18.5" / "pitched in 18.0" / "kicked in 16.0"
    - "Player managed 12.8" / "rolled for 19.3" / "had 27.02"
    """
    claims = []

    # Pattern: "Player's XX.X" (possessive + number)
    poss_name = r"([A-Z][A-Za-z'.]+(?:\s+(?:[A-Z][A-Za-z'.]+|(?:Jr|Sr|St|de|van|of)\.?)){0,3})"
    for m in re.finditer(
        rf"{poss_name}\u2019s\s+(\d+\.\d+)(?:\s*-?\s*point)?|"
        rf"{poss_name}'s\s+(\d+\.\d+)(?:\s*-?\s*point)?",
        text
    ):
        # Handle either curly or straight apostrophe match
        name = (m.group(1) or m.group(3) or "").strip()
        pts = m.group(2) or m.group(4)
        if not name or not pts:
            continue
        if name.split()[0] in ("Week", "The", "Your", "That", "This", "And",
                                "But", "Since", "You", "At", "In", "On", "By",
                                "Or", "If", "So", "No", "Every", "One", "Two",
                                "Three", "After", "For"):
            continue
        claims.append((name, float(pts)))

    # Pattern: "Player verb XX.X"
    # Player name: 1-4 words, each starting with uppercase or being a connector
    player_name = r"([A-Z][A-Za-z'.]+(?:\s+(?:[A-Z][A-Za-z'.]+|(?:Jr|Sr|St|de|van|of)\.?)){0,3})"
    verbs = (
        r"(?:added|scored|contributed|dropped|erupted\s+for|posted|"
        r"went\s+off\s+for|chipped\s+in|pitched\s+in|kicked\s+in|"
        r"managed|rolled\s+for|had|put\s+up|delivered|exploded\s+for|"
        r"led.*?with)"
    )
    for m in re.finditer(
        rf"{player_name}\s+{verbs}\s+(\d+\.\d+)",
        text
    ):
        name = m.group(1).strip()
        # Filter out non-player prefixes
        if name.split()[0] in ("Week", "The", "Your", "That", "This", "And",
                                "But", "Since", "You", "At", "In", "On", "By",
                                "Or", "If", "So", "No", "Every", "One", "Two",
                                "Three", "After", "For"):
            continue
        claims.append((name, float(m.group(2))))

    # Pattern: "Player (XX.X)" — parenthetical score
    for m in re.finditer(
        r"([A-Z][A-Za-z'. \-]+?)\s+\((\d+\.\d+)\)",
        text
    ):
        name = m.group(1).strip()
        if name in ("Week", "The", "Your", "That", "This", "And", "But", "Since",
                     "You", "At", "In", "On", "By", "Or", "If", "So", "No"):
            continue
        claims.append((name, float(m.group(2))))

    return claims


def build_prev_weeks_scorers(week: int) -> dict[str, list[dict]]:
    """Build scorer lookup from all previous weeks' data files."""
    lookup: dict[str, list[dict]] = {}
    for w in range(1, week):
        path = WEEKS_DIR / f"week{w}_data.json"
        if not path.exists():
            continue
        try:
            prev_data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for m in prev_data.get("matchups", []):
            for side in ["team1", "team2"]:
                team = m[side]
                for scorer in team.get("top_scorers", []):
                    key = scorer["name"].lower().strip()
                    lookup.setdefault(key, []).append({
                        "week": w,
                        "points": scorer["points"],
                        "name": scorer["name"],
                    })
    return lookup


def verify_player_scores(content: dict, data: dict, errors: list, warnings: list):
    """Verify player score claims against matchup top_scorers."""
    # Build set of team names (normalized) to filter out
    team_names = {normalize_team(s["team_name"]) for s in data.get("standings", [])}
    current_week = data.get("meta", {}).get("week", 0)
    prev_scorers = build_prev_weeks_scorers(current_week)

    # Build lookup: player_name -> {team_name, points}
    scorer_lookup: dict[str, list[dict]] = {}
    for m in data.get("matchups", []):
        for side in ["team1", "team2"]:
            team = m[side]
            for scorer in team.get("top_scorers", []):
                key = scorer["name"].lower().strip()
                scorer_lookup.setdefault(key, []).append({
                    "team_name": team["team_name"],
                    "points": scorer["points"],
                    "name": scorer["name"],
                })

    # Scan all blurb text
    for r in content.get("rankings", []):
        blurb = r.get("blurb", "")
        team_name = r.get("team_name", "")
        claims = extract_player_score_claims(blurb)

        for player, claimed_pts in claims:
            # Skip if player name matches a team name
            if normalize_team(player) in team_names:
                continue

            key = player.lower().strip()
            entries = scorer_lookup.get(key, [])

            if not entries:
                # Try partial match (last name)
                parts = player.split()
                if len(parts) >= 2:
                    last = parts[-1].lower()
                    entries = [
                        e for k, elist in scorer_lookup.items()
                        for e in elist
                        if last in k
                    ]

            if not entries:
                warnings.append(
                    f"Rank {r.get('rank')} ({team_name}): "
                    f"'{player} {claimed_pts}' not found in any top_scorers "
                    f"(may be outside top 5)"
                )
                continue

            # Check if any entry matches the claimed score
            matched = any(
                abs(e["points"] - claimed_pts) < 0.01
                for e in entries
            )
            if not matched:
                # Check if it matches a previous week's data (callback reference)
                prev_key = player.lower().strip()
                prev_entries = prev_scorers.get(prev_key, [])
                if not prev_entries and len(player.split()) >= 2:
                    last = player.split()[-1].lower()
                    prev_entries = [
                        e for k, elist in prev_scorers.items()
                        for e in elist
                        if last in k
                    ]
                is_callback = any(
                    abs(e["points"] - claimed_pts) < 0.01
                    for e in prev_entries
                )
                if is_callback:
                    # It's a reference to a previous week — not an error
                    pass
                else:
                    actual = ", ".join(f"{e['name']}={e['points']}" for e in entries)
                    errors.append(
                        f"Rank {r.get('rank')} ({team_name}): "
                        f"claims '{player} {claimed_pts}' but data shows: {actual}"
                    )

    # Also scan essay
    essay = content.get("essay", "")
    claims = extract_player_score_claims(essay)
    for player, claimed_pts in claims:
        if normalize_team(player) in team_names:
            continue
        key = player.lower().strip()
        entries = scorer_lookup.get(key, [])
        if not entries:
            parts = player.split()
            if len(parts) >= 2:
                last = parts[-1].lower()
                entries = [
                    e for k, elist in scorer_lookup.items()
                    for e in elist
                    if last in k
                ]
        if entries:
            matched = any(abs(e["points"] - claimed_pts) < 0.01 for e in entries)
            if not matched:
                # Check if it matches a previous week's data
                prev_key = player.lower().strip()
                prev_entries = prev_scorers.get(prev_key, [])
                if not prev_entries and len(player.split()) >= 2:
                    last = player.split()[-1].lower()
                    prev_entries = [
                        e for k, elist in prev_scorers.items()
                        for e in elist
                        if last in k
                    ]
                is_callback = any(
                    abs(e["points"] - claimed_pts) < 0.01
                    for e in prev_entries
                )
                if not is_callback:
                    actual = ", ".join(f"{e['name']}={e['points']}" for e in entries)
                    errors.append(
                        f"Essay: claims '{player} {claimed_pts}' "
                        f"but data shows: {actual}"
                    )


def verify_h2h_claims(content: dict, data: dict, errors: list, warnings: list):
    """Verify H2H record claims (e.g. '3-5 all-time', '8-0 against')."""
    # Build H2H lookup from matchups
    h2h_lookup = {}
    for m in data.get("matchups", []):
        h2h = m.get("h2h", {})
        if h2h:
            t1 = normalize_team(m["team1"]["team_name"])
            t2 = normalize_team(m["team2"]["team_name"])
            h2h_lookup[(t1, t2)] = h2h
            h2h_lookup[(t2, t1)] = {
                "team1_wins": h2h["team2_wins"],
                "team2_wins": h2h["team1_wins"],
                "total_games": h2h["total_games"],
            }

    # Scan blurbs for H2H patterns
    h2h_pattern = re.compile(r"(\d+)-(\d+)\s+(?:all[- ]time|against|head-to-head|h2h)")

    all_texts = []
    for r in content.get("rankings", []):
        all_texts.append((f"Rank {r.get('rank')} ({r.get('team_name')})", r.get("blurb", ""), r.get("team_name", "")))
    all_texts.append(("Essay", content.get("essay", ""), ""))

    for context_label, text, team_name in all_texts:
        for m in h2h_pattern.finditer(text):
            claimed_w = int(m.group(1))
            claimed_l = int(m.group(2))
            # Try to find matching H2H data
            if team_name:
                nt = normalize_team(team_name)
                matched = False
                for (t1, t2), h2h in h2h_lookup.items():
                    if nt == t1 or nt == t2:
                        if nt == t1:
                            actual_w = h2h["team1_wins"]
                            actual_l = h2h["team2_wins"]
                        else:
                            actual_w = h2h["team2_wins"]
                            actual_l = h2h["team1_wins"]
                        if claimed_w == actual_w and claimed_l == actual_l:
                            matched = True
                            break
                        elif claimed_w == actual_l and claimed_l == actual_w:
                            # Might be citing opponent's perspective
                            matched = True
                            break
                if not matched and team_name:
                    warnings.append(
                        f"{context_label}: H2H claim '{claimed_w}-{claimed_l}' "
                        f"could not be verified against matchup data"
                    )


def verify_elo_claims(content: dict, data: dict, errors: list, warnings: list):
    """Verify Elo-related claims (jumped/dropped XX.X, hit XXXX.X)."""
    standings = data.get("standings", [])

    elo_change_pattern = re.compile(
        r"[Ee]lo\s+(?:jumped|dropped|rose|fell|gained|lost|moved|changed|spiked?)\s+"
        r"(\d+\.?\d*)\s*(?:points?)?",
    )
    elo_hit_pattern = re.compile(
        r"[Ee]lo\s+(?:hit|reached|climbed\s+to|sits?\s+at)\s+(\d{3,4}\.?\d*)"
    )

    for r in content.get("rankings", []):
        blurb = r.get("blurb", "")
        team_name = r.get("team_name", "")
        standing = find_team_in_standings(team_name, standings)
        if not standing:
            continue

        for m in elo_change_pattern.finditer(blurb):
            claimed = float(m.group(1))
            actual = abs(standing.get("elo_change", 0))
            if abs(claimed - actual) > 0.15:
                errors.append(
                    f"Rank {r.get('rank')} ({team_name}): "
                    f"claims Elo change of {claimed} but data shows "
                    f"{standing.get('elo_change')}"
                )

        for m in elo_hit_pattern.finditer(blurb):
            claimed = float(m.group(1))
            actual_current = standing.get("current_elo", 0)
            actual_peak = standing.get("peak_elo", 0)
            if abs(claimed - actual_current) > 0.15 and abs(claimed - actual_peak) > 0.15:
                errors.append(
                    f"Rank {r.get('rank')} ({team_name}): "
                    f"claims Elo of {claimed} but data shows "
                    f"current={actual_current}, peak={actual_peak}"
                )


def verify_total_points(content: dict, data: dict, errors: list, warnings: list):
    """Verify total-points claims (e.g. '479.9 total points')."""
    standings = data.get("standings", [])
    pf_pattern = re.compile(r"(\d{2,3}\.\d)\s+(?:total\s+)?points?(?:\s+(?:for|through|this\s+season))?")

    for r in content.get("rankings", []):
        blurb = r.get("blurb", "")
        team_name = r.get("team_name", "")
        standing = find_team_in_standings(team_name, standings)
        if not standing:
            continue

        for m in pf_pattern.finditer(blurb):
            claimed = float(m.group(1))
            actual_pf = standing.get("pf", 0)
            actual_wp = standing.get("week_points", 0)
            # Could be either season total or week points
            if abs(claimed - actual_pf) > 0.15 and abs(claimed - actual_wp) > 0.15:
                # Only flag if it looks like a season total (>200)
                if claimed > 200:
                    errors.append(
                        f"Rank {r.get('rank')} ({team_name}): "
                        f"claims {claimed} total points but data shows "
                        f"pf={actual_pf}, week_points={actual_wp}"
                    )


def verify_margin_claims(content: dict, data: dict, errors: list, warnings: list):
    """Verify margin claims (won by XX.X, lost by XX.X, XX.X-point margin)."""
    matchups = data.get("matchups", [])

    # Pattern 1: "won/lost/beat by XX.X"
    by_pattern = re.compile(
        r"(?:won\s+by|lost\s+by|beat\s+\S+\s+by|margin\s+of|"
        r"defeated\s+\S+\s+by)\s+(\d+\.\d+)",
    )

    # Pattern 2: "XX.X-point loss/blowout/beatdown/thrashing" (margin-scale only)
    margin_label_pattern = re.compile(
        r"(\d+\.\d+)[- ]point\s+(?:loss|defeat|blowout|demolition|"
        r"evisceration|beatdown|thrashing|margin)",
    )

    for r in content.get("rankings", []):
        blurb = r.get("blurb", "")
        team_name = r.get("team_name", "")
        matchup = find_matchup_for_team(team_name, matchups)
        if not matchup:
            continue

        actual_margin = matchup.get("margin", 0)

        for pat in [by_pattern, margin_label_pattern]:
            for m in pat.finditer(blurb):
                claimed = float(m.group(1))
                # Skip values that look like weekly scores (> 80), not margins
                if claimed > 80:
                    continue
                if abs(claimed - actual_margin) > 0.15:
                    errors.append(
                        f"Rank {r.get('rank')} ({team_name}): "
                        f"claims margin {claimed} but data shows {actual_margin}"
                    )

    # Also check essay for margin claims
    essay = content.get("essay", "")
    for m in re.finditer(r"by\s+(\d+\.\d+)\s+point", essay):
        claimed = float(m.group(1))
        if claimed > 80:
            continue
        if not any(abs(claimed - mx.get("margin", 0)) < 0.15 for mx in matchups):
            warnings.append(
                f"Essay: margin claim '{claimed}' doesn't match any matchup margin"
            )


def verify_superlative_claims(content: dict, data: dict, errors: list, warnings: list):
    """Verify high/low scorer claims against awards."""
    awards = data.get("awards", {})

    # Check essay and blurbs for superlative claims
    all_text = content.get("essay", "")
    for r in content.get("rankings", []):
        all_text += " " + r.get("blurb", "")

    # "highest score" / "high scorer" / "top scorer" claims
    if awards.get("high_scorer"):
        hs = awards["high_scorer"]
        # Check if essay/blurbs claim a different high scorer
        high_pattern = re.compile(
            r"(?:highest|high|top)\s+scor(?:e|er|ing)\s+(?:of|in|this)\s+(?:the\s+)?(?:week|Week\s+\d+)",
            re.IGNORECASE,
        )
        for m in high_pattern.finditer(all_text):
            # Look for score near the match
            vicinity = all_text[max(0, m.start() - 200):m.end() + 200]
            score_m = re.search(r"(\d{2,3}\.\d{1,2})", vicinity)
            if score_m:
                claimed = float(score_m.group(1))
                actual = hs["points"]
                if abs(claimed - actual) > 0.15:
                    warnings.append(
                        f"Superlative: claims high score of {claimed} "
                        f"but awards shows {actual}"
                    )

    # "lowest score" / "low scorer" claims
    if awards.get("low_scorer"):
        ls = awards["low_scorer"]
        low_pattern = re.compile(
            r"(?:lowest|low)\s+(?:total|score|scorer)\s+(?:of|in|this)\s+(?:the\s+)?(?:week|league)",
            re.IGNORECASE,
        )
        for m in low_pattern.finditer(all_text):
            vicinity = all_text[max(0, m.start() - 200):m.end() + 200]
            score_m = re.search(r"(\d{2,3}\.\d{1,2})", vicinity)
            if score_m:
                claimed = float(score_m.group(1))
                actual = ls["points"]
                if abs(claimed - actual) > 0.15:
                    warnings.append(
                        f"Superlative: claims low score of {claimed} "
                        f"but awards shows {actual}"
                    )


def verify_week_score_claims(content: dict, data: dict, errors: list, warnings: list):
    """Verify weekly score claims (e.g. 'your 191.34-point week')."""
    standings = data.get("standings", [])
    # Pattern: "XXX.XX-point" in context of a team
    score_pattern = re.compile(r"(\d{2,3}\.\d{1,2})[- ]point")

    for r in content.get("rankings", []):
        blurb = r.get("blurb", "")
        team_name = r.get("team_name", "")
        standing = find_team_in_standings(team_name, standings)
        if not standing:
            continue

        actual_wp = standing.get("week_points", 0)
        for m in score_pattern.finditer(blurb):
            claimed = float(m.group(1))
            # Only flag if it looks like a weekly score (90-250 range)
            # and doesn't match week_points or any other team's week_points
            if 90 < claimed < 250 and abs(claimed - actual_wp) > 0.15:
                # Check if it matches opponent's score or any other known value
                matchup = find_matchup_for_team(team_name, data.get("matchups", []))
                if matchup:
                    opp_pts = [matchup["team1"]["points"], matchup["team2"]["points"]]
                    margin = matchup.get("margin", 0)
                    if any(abs(claimed - p) < 0.15 for p in opp_pts):
                        continue  # Matches opponent score, fine
                    if abs(claimed - margin) < 0.15:
                        continue  # Matches margin
                # Check if it matches any team's week_points
                if any(abs(claimed - s.get("week_points", 0)) < 0.15 for s in standings):
                    continue
                warnings.append(
                    f"Rank {r.get('rank')} ({team_name}): "
                    f"score claim '{claimed}' doesn't match "
                    f"week_points={actual_wp}"
                )


def verify_prev_rank_claims(content: dict, data: dict, errors: list, warnings: list):
    """Verify claims about ranks in previous weeks against prior content files."""
    week = data.get("meta", {}).get("week", 0)
    if week <= 1:
        return

    # Look for patterns like "Fifth in Week 1", "ranked 2nd in Week 1",
    # "number one in Week 2", "ranked Nth last week"
    rank_words = {
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
        "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
        "eleventh": 11, "twelfth": 12, "last": 12, "dead last": 12,
        "number one": 1, "number two": 2, "number three": 3,
        "number four": 4, "number five": 5,
    }

    prev_week_pattern = re.compile(
        r"(?:(?:ranked?\s+)?(?:(\w+(?:\s+\w+)?)\s+(?:in|during)\s+Week\s+(\d+))|"
        r"(?:(?:preseason\s+)?(?:number\s+)?(\w+)\s+(?:in\s+the\s+)?preseason))",
        re.IGNORECASE,
    )

    for r in content.get("rankings", []):
        blurb = r.get("blurb", "")
        team_name = r.get("team_name", "")

        for m in prev_week_pattern.finditer(blurb):
            if m.group(1) and m.group(2):
                rank_word = m.group(1).lower()
                ref_week = int(m.group(2))
                claimed_rank = rank_words.get(rank_word)
                if claimed_rank is None:
                    # Try parsing as ordinal number
                    num_m = re.match(r"(\d+)(?:st|nd|rd|th)", rank_word)
                    if num_m:
                        claimed_rank = int(num_m.group(1))

                if claimed_rank and ref_week < week:
                    prev_content = load_prev_content(ref_week)
                    if prev_content:
                        for pr in prev_content.get("rankings", []):
                            if teams_match(pr.get("team_name", ""), team_name):
                                if pr["rank"] != claimed_rank:
                                    errors.append(
                                        f"Rank {r.get('rank')} ({team_name}): "
                                        f"claims ranked {rank_word} in Week {ref_week} "
                                        f"but week{ref_week}_content.json shows "
                                        f"rank={pr['rank']}"
                                    )
                                break


def verify_team_count_claims(content: dict, data: dict, errors: list, warnings: list):
    """Verify claims about how many teams did X (e.g. 'nine other teams')."""
    count_words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12,
    }

    # "beat N of the N other teams" / "enough to beat N other teams"
    beat_pattern = re.compile(
        r"(?:beat|outscore[d]?)\s+(\w+)\s+(?:of\s+the\s+)?(?:\w+\s+)?(?:other\s+)?teams?",
        re.IGNORECASE,
    )

    standings = data.get("standings", [])

    all_text = content.get("essay", "")
    for r in content.get("rankings", []):
        all_text += " " + r.get("blurb", "")

    for m in beat_pattern.finditer(all_text):
        word = m.group(1).lower()
        claimed_count = count_words.get(word)
        if claimed_count is None:
            try:
                claimed_count = int(word)
            except ValueError:
                continue

        # The context should tell us which team's score we're comparing
        # For now, just flag if the count doesn't match possible values
        # (a team scoring X can beat 0-11 other teams)
        if claimed_count > 11:
            errors.append(
                f"Claims beating {claimed_count} teams but only 11 opponents exist"
            )


def run_tier2(content: dict, data: dict) -> dict:
    """Run all Tier 2 content checks."""
    errors = []
    warnings = []

    verify_player_scores(content, data, errors, warnings)
    verify_h2h_claims(content, data, errors, warnings)
    verify_elo_claims(content, data, errors, warnings)
    verify_total_points(content, data, errors, warnings)
    verify_margin_claims(content, data, errors, warnings)
    verify_superlative_claims(content, data, errors, warnings)
    verify_week_score_claims(content, data, errors, warnings)
    verify_prev_rank_claims(content, data, errors, warnings)
    verify_team_count_claims(content, data, errors, warnings)

    passed = 9 - (1 if errors else 0)  # count of check categories without errors
    failed = 1 if errors else 0

    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_pretty(week: int, tier1: dict, tier2: dict) -> str:
    lines = []
    lines.append(f"WEEK {week} CONTENT VALIDATION")
    lines.append("=" * 40)
    lines.append("")

    # Tier 1
    t1_total = tier1["passed"] + tier1["failed"]
    if tier1["failed"] == 0:
        lines.append(f"TIER 1 (Structural): {tier1['passed']}/{t1_total} PASS")
    else:
        lines.append(f"TIER 1 (Structural): {tier1['passed']}/{t1_total} "
                      f"({tier1['failed']} FAILED)")
        for e in tier1["errors"]:
            lines.append(f"  [FAIL] {e}")

    lines.append("")

    # Tier 2
    t2_errors = len(tier2["errors"])
    t2_warnings = len(tier2["warnings"])
    if t2_errors == 0 and t2_warnings == 0:
        lines.append("TIER 2 (Content): ALL CHECKS PASS")
    else:
        lines.append("TIER 2 (Content):")
        for e in tier2["errors"]:
            lines.append(f"  [FAIL] {e}")
        for w in tier2["warnings"]:
            lines.append(f"  [WARN] {w}")

    lines.append("")

    total_errors = len(tier1["errors"]) + t2_errors
    verdict = "PASS" if total_errors == 0 else "FAIL"
    parts = []
    if total_errors:
        parts.append(f"{total_errors} error{'s' if total_errors != 1 else ''}")
    if t2_warnings:
        parts.append(f"{t2_warnings} warning{'s' if t2_warnings != 1 else ''}")
    if not parts:
        parts.append("clean")

    lines.append(f"VERDICT: {verdict} ({', '.join(parts)})")
    return "\n".join(lines)


def format_json(week: int, tier1: dict, tier2: dict) -> str:
    total_errors = len(tier1["errors"]) + len(tier2["errors"])
    result = {
        "week": week,
        "verdict": "PASS" if total_errors == 0 else "FAIL",
        "tier1": tier1,
        "tier2": tier2,
        "summary": (
            f"{tier1['passed']} of {tier1['passed'] + tier1['failed']} "
            f"structural checks passed. "
            f"{len(tier2['errors'])} content errors, "
            f"{len(tier2['warnings'])} warnings."
        ),
    }
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Verify weekly content JSON against week data"
    )
    parser.add_argument("--week", type=int, required=True, help="Week number")
    parser.add_argument("--pretty", action="store_true", help="Human-readable output")
    parser.add_argument(
        "--fix-suggestions", action="store_true",
        help="Show suggested fixes for errors"
    )
    args = parser.parse_args()

    content_path = WEEKS_DIR / f"week{args.week}_content.json"
    data_path = WEEKS_DIR / f"week{args.week}_data.json"

    if not content_path.exists():
        print(f"ERROR: {content_path} not found")
        sys.exit(2)
    if not data_path.exists():
        print(f"ERROR: {data_path} not found")
        sys.exit(2)

    content = load_json(content_path)
    data = load_json(data_path)

    tier1 = run_tier1(content, data)
    tier2 = run_tier2(content, data)

    if args.pretty:
        print(format_pretty(args.week, tier1, tier2))
    else:
        print(format_json(args.week, tier1, tier2))

    total_errors = len(tier1["errors"]) + len(tier2["errors"])
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
