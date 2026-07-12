"""Noninterference hard gate (1h): post-cutoff evidence must not alter the
as-of-cutoff writer-facing projection.

The fixture populates ALL EIGHT writer-facing surfaces at the cutoff (so the
byte-identical checks are non-vacuous), and each surface is proven
DETECTOR-ACTIVE FIRST -- an isolated post-cutoff delta genuinely changes it at
all-evidence -- so noninterference passes for the RIGHT reason. Two axes vary:
post-cutoff MESSAGES (arcs + jokes + relevancy + sentiment + highlights are
recomputed FROM messages) and, independently, a post-cutoff PREDICTION
(predictions_source is the only independently varied input). Synthetic, no I/O.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_chat_context import (
    NONINTERFERENCE_SECTIONS,  # noqa: E402
    build_context_dict,
    noninterference_divergences,
)

C = datetime(2025, 10, 7, 6, 59, 59, tzinfo=timezone.utc)  # ~ week 5 cutoff
# All-evidence: a LATE cutoff (not None, which would crash cutoff.strftime). The
# week-5 window_start is unchanged, so its window [Sep30, Dec1] admits the
# post-cutoff evidence, making even the windowed surfaces detector-active.
LATE = datetime(2025, 12, 1, 6, 59, 59, tzinfo=timezone.utc)

NAME_MAP = {"Brent Boone": {}, "Matt Russell": {}}
IDENTITY_CHAIN = {
    "by_roster_id": {
        "1": {"whatsapp_name": "Brent Boone", "team_name": "Chudders"},
        "2": {"whatsapp_name": "Matt Russell", "team_name": "Russellmania"},
    }
}
LEAGUE_MEMORY = {"culture": {"activity_triggers": ["Trade announcements"]}}
WEEK_DATA = {
    "matchups": [
        {
            "team1": {
                "roster_id": 1,
                "team_name": "Chudders",
                "points": 110,
                "top_scorers": [{"name": "Mahomes", "points": 31.0}],
            },
            "team2": {
                "roster_id": 2,
                "team_name": "Russellmania",
                "points": 95,
                "top_scorers": [{"name": "Bijan", "points": 4.0}],
            },
            "winner": "Chudders",
            "margin": 15,
        }
    ]
}


def _M(sender, ts, text):
    return {"sender": sender, "timestamp_utc": ts, "text": text, "is_system": False}


# Base evidence, all in the week-5 window [Sep30, Oct7]. Deliberately laid out so
# HIGH (idx 0) and MEDIUM (idx 6) survive dedup and the cluster (idx 10-12) is
# clear of both relevancy items' highlight-exclusion zones.
BASE = [
    _M(
        "Brent Boone",
        "2025-10-01T10:00:00Z",
        "russellmania is washed and overrated, easy win",
    ),  # HIGH
    _M("Brent Boone", "2025-10-01T11:00:00Z", "who says no to this trade"),
    _M("Matt Russell", "2025-10-01T11:02:00Z", "i want to trade my rb"),
    _M("Brent Boone", "2025-10-01T11:04:00Z", "that was a robbery"),
    _M("Brent Boone", "2025-10-02T10:00:00Z", "taco tuesday again lol"),
    _M("Matt Russell", "2025-10-02T10:02:00Z", "taco time so good"),
    _M("Matt Russell", "2025-10-03T10:00:00Z", "mahomes is a bust this year"),  # MEDIUM
    _M("Brent Boone", "2025-10-03T12:00:00Z", "ok cool thanks man"),
    _M("Matt Russell", "2025-10-03T13:00:00Z", "sounds good then friend"),
    _M("Brent Boone", "2025-10-04T09:00:00Z", "anyway moving on now"),
    _M("Brent Boone", "2025-10-05T10:00:00Z", "lol"),  # cluster
    _M("Matt Russell", "2025-10-05T10:01:00Z", "haha yeah man"),
    _M("Brent Boone", "2025-10-05T10:02:00Z", "for sure man"),
]
BASE_PREDS = {
    "predictions": [
        {
            "author_whatsapp": "Brent Boone",
            "subject": "mahomes is elite this year",
            "made_at": "2025-10-01T09:00:00Z",
            "quote_block": [],
        },
        {
            "author_whatsapp": "Matt Russell",
            "subject": "chudders is a fraud this year",
            "made_at": "2025-10-01T09:30:00Z",
            "quote_block": [],
        },
    ]
}
# A post-cutoff prediction that RESOLVES (positive about Russellmania, who lost ->
# aging_badly) and mentions a playing team (callback). Admitted only at LATE.
FUTURE_PRED = {
    "author_whatsapp": "Brent Boone",
    "subject": "russellmania is the best championship team this year",
    "made_at": "2025-10-20T00:00:00Z",
    "quote_block": [],
}

# Isolated per-surface post-cutoff (Oct 20) MESSAGE deltas -- each appended far
# from base scored items so dedup / highlight-exclusion don't swallow it.
DELTA = {
    "active_arcs_this_week": [
        _M("Brent Boone", "2025-10-20T10:00:00Z", "who says no to this trade steal")
    ],
    "league_memory": [
        _M("Brent Boone", "2025-10-20T10:00:00Z", "taco night again woo")
    ],
    "high_relevancy": [
        _M(
            "Matt Russell",
            "2025-10-20T10:00:00Z",
            "chudders is washed and overrated easy dub win",
        )
    ],
    "medium_relevancy": [
        _M("Brent Boone", "2025-10-20T10:00:00Z", "mahomes is a flop lately honestly")
    ],
    "this_weeks_chat_highlights": [
        _M("Brent Boone", "2025-10-20T10:00:00Z", "yo"),
        _M("Matt Russell", "2025-10-20T10:01:00Z", "sup dude"),
        _M("Brent Boone", "2025-10-20T10:02:00Z", "nada man"),
    ],
    # A burst crossing the winner's count>10 "notable" boundary changes sentiment.
    "sentiment_snapshot": [
        _M("Brent Boone", f"2025-10-20T10:0{i}:00Z", "ok") for i in range(6)
    ],
}
POST = [m for delta in DELTA.values() for m in delta]


def _build(messages, cutoff, predictions=None):
    return build_context_dict(
        messages,
        NAME_MAP,
        IDENTITY_CHAIN,
        LEAGUE_MEMORY,
        WEEK_DATA,
        predictions or BASE_PREDS,
        2025,
        5,
        False,
        cutoff,
    )


def test_noninterference_all_sections_byte_identical_at_cutoff():
    """Every one of the 8 writer-facing surfaces populates at C AND is
    byte-identical whether or not the post-cutoff messages are present."""
    base_C = _build(BASE, C)
    full_C = _build(BASE + POST, C)
    for section in NONINTERFERENCE_SECTIONS:
        val = base_C[section]
        nonempty = val.get("running_jokes") if section == "league_memory" else val
        assert nonempty, f"fixture must populate {section} at C (non-vacuous)"
        assert full_C[section] == base_C[section], f"{section} leaked post-cutoff data"
    # The machine gate's core agrees: nothing diverges (post messages truncated).
    divs = noninterference_divergences(
        BASE + POST,
        NAME_MAP,
        IDENTITY_CHAIN,
        LEAGUE_MEMORY,
        BASE_PREDS,
        2025,
        5,
        False,
        C,
        WEEK_DATA,
    )
    assert divs == []


def test_each_message_surface_is_detector_active():
    """Every message-driven surface genuinely reacts to its post-cutoff delta at
    all-evidence -- so its noninterference-at-C is meaningful, not vacuous."""
    base_late = _build(BASE, LATE)
    for section, delta in DELTA.items():
        assert (
            _build(BASE + delta, LATE)[section] != base_late[section]
        ), f"{section} is not detector-active"


def test_prediction_axis_noninterference_and_detector_active():
    """The independently-varied injectable: a post-cutoff prediction is excluded
    at C (fail-closed on made_at) and, at LATE, changes BOTH resolved_predictions
    and the prediction callbacks."""
    p_full = {"predictions": BASE_PREDS["predictions"] + [FUTURE_PRED]}
    # noninterference at C -- same cutoff, two prediction worlds.
    base_C = _build(BASE, C, BASE_PREDS)
    full_C = _build(BASE, C, p_full)
    assert base_C["resolved_predictions"] == full_C["resolved_predictions"]
    assert base_C["suggested_callbacks"] == full_C["suggested_callbacks"]
    # detector-active at LATE.
    base_L = _build(BASE, LATE, BASE_PREDS)
    full_L = _build(BASE, LATE, p_full)
    assert full_L["resolved_predictions"] != base_L["resolved_predictions"]
    pred_cbs_base = [
        c for c in base_L["suggested_callbacks"] if c["source"] == "prediction"
    ]
    pred_cbs_full = [
        c for c in full_L["suggested_callbacks"] if c["source"] == "prediction"
    ]
    assert pred_cbs_full != pred_cbs_base
