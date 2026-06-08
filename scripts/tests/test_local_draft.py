"""Tests for scripts/local_draft.py — context builders + section prompts.

local_draft.py had zero coverage before Phase 1c. These are pure-function tests
(no Ollama / no network): they exercise the context builders on a minimal week
fixture and lock the SECTION_PROMPTS against the two failure modes that matter
when editing them — a stray brace breaking `.format(week=...)`, and the
new-field guidance silently dropping out.
"""

from scripts.local_draft import (
    SECTION_PROMPTS,
    build_essay_context,
    build_light_context,
    build_rankings_context,
)

# Minimal week_data mirroring the live shape the builders consume. game_context
# is the thin v2 form (game_id + one_liner + opponent); standings carry the
# compact fields build_essay_context reads (momentum.label, margin_this_week).
MIN_WEEK = {
    "matchups": [
        {
            "team1": {
                "team_name": "Team A",
                "points": 120.5,
                "top_scorers": [
                    {
                        "name": "Player X",
                        "game_context": {
                            "game_id": "2025_05_TB_SEA",
                            "one_liner": "7 rec, 163 yd, 1 TD vs. the Seahawks",
                            "opponent": "SEA",
                        },
                    }
                ],
            },
            "team2": {"team_name": "Team B", "points": 99.0, "top_scorers": []},
        }
    ],
    "awards": {
        "top_performer": {
            "name": "Player X",
            "game_context": {"game_id": "2025_05_TB_SEA"},
        }
    },
    "standings": [
        {
            "team_name": "Team A",
            "record": "4-1",
            "rank": 1,
            "points_for": 600.0,
            "momentum": {"label": "hot"},
            "margin_this_week": 21.5,
        },
        {
            "team_name": "Team B",
            "record": "1-4",
            "rank": 12,
            "points_for": 400.0,
            "momentum": {"label": "cooling"},
            "margin_this_week": -21.5,
        },
    ],
    "previous_weeks_summary": "Week 4 recap.",
    "historical_context": {"highest_score": 200.0},
    "team_profiles_summary": [{"team_name": "Team A", "ranks": {"qb": 1}}],
}

NFLGAME_TOKENS = [
    "game_id",
    "team_stats",
    "key_injuries",
    "rest_days",
    "div_game",
    "spread_line",
]


def test_essay_context_builds():
    out = build_essay_context(MIN_WEEK, {}, None)
    assert isinstance(out, str) and out
    assert "MATCHUP RESULTS" in out and "STANDINGS" in out


def test_rankings_context_builds():
    out = build_rankings_context(MIN_WEEK, {})
    assert isinstance(out, str) and out
    assert "FULL STANDINGS" in out


def test_light_context_builds():
    out = build_light_context(MIN_WEEK, {})
    assert isinstance(out, str) and out


def test_section_prompts_format_clean():
    # Every section must survive .format(week=N) — a stray single brace anywhere
    # (the JSON examples escape theirs as {{ }}) would raise here.
    for name, prompt in SECTION_PROMPTS.items():
        prompt.format(week=5)  # raises KeyError/ValueError/IndexError on a bad brace


def test_enriched_prompts_mention_new_fields():
    blob = SECTION_PROMPTS["essay"] + SECTION_PROMPTS["rankings"]
    present = [t for t in NFLGAME_TOKENS if t in blob]
    assert len(present) >= 4, f"only {present} present; expected >= 4 NFLGame tokens"


def test_week_interpolates():
    # The {week} field must actually interpolate (catches a silent {{week}}
    # mis-escape that would render the literal token instead of the number).
    assert "week 7" in SECTION_PROMPTS["essay"].format(week=7)
    assert "week 7" in SECTION_PROMPTS["rankings"].format(week=7)
