"""Parser fixes for the WhatsApp segmentation + system-classification bugs.

Pins the 2026-07 repair:
  DEFECT A - iOS prefixes attachment/system message-start lines with U+200E
             before "[". The old ^\\[ anchor failed to match them, swallowing
             1,475 real lines into the prior message (wrong-sender + lost media).
  DEFECT B - System/automated events (join/add/create/pin/rename/phone/delete)
             are stamped under a member name with a leading U+200E in the body;
             they must be flagged is_system, not attributed to the member. A
             POLL is a member action, NOT a system event: it keeps its sender
             and is flagged is_poll (see test_poll_is_member_message_not_system).
  DEFECT D - Attachment markers + bidi controls must not leak into stored text.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parse_whatsapp import LINE_RE, parse_chat  # noqa: E402

LRM = "\u200e"  # left-to-right mark
NBSP = "\u202f"  # narrow no-break space (WhatsApp "~ Name" senders)


def _write(tmp_path, lines):
    p = tmp_path / "_chat.txt"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def test_line_re_consumes_leading_lrm():
    # DEFECT A: a message-start line prefixed with U+200E must still segment.
    plain = "[9/7/23, 5:58:17\u202fPM] Karim: hello"
    marked = LRM + "[9/7/23, 5:58:17\u202fPM] Karim: hi"
    assert LINE_RE.match(plain)
    assert LINE_RE.match(marked)


def test_lrm_prefixed_media_line_is_its_own_message(tmp_path):
    # DEFECT A: the U+200E media line must NOT be swallowed into Karim's message.
    lines = [
        "[9/7/23, 5:58:17\u202fPM] Karim: Let's goo!",
        LRM
        + "[9/7/23, 6:20:46\u202fPM] Brent Boone: "
        + LRM
        + "<attached: 00000033-GIF.mp4>",
    ]
    data = parse_chat(_write(tmp_path, lines))
    msgs = data["messages"]
    assert len(msgs) == 2, "U+200E media line was swallowed instead of segmented"
    assert msgs[0]["sender"] == "Karim"
    assert msgs[0]["text"] == "Let's goo!"
    # Second line correctly attributed to Brent, media extracted, prose cleaned.
    assert msgs[1]["sender"] == "Brent Boone"
    assert msgs[1]["is_system"] is False
    assert msgs[1]["media"] == "00000033-GIF.mp4"
    assert "<attached:" not in msgs[1]["text"]


def test_system_notification_flagged_not_attributed(tmp_path):
    # DEFECT B: text-start U+200E that is NOT an attachment -> system event.
    lines = [
        "[9/7/23, 3:54:06\u202fPM] Sacko: " + LRM + "Sacko created this group",
        "[9/7/23, 5:34:37\u202fPM] ~"
        + NBSP
        + "Harlow: "
        + LRM
        + "~"
        + NBSP
        + "Harlow joined using a group link",
        "[7/15/24, 11:33:35\u202fAM] Sacko: " + LRM + "Sacko pinned a message",
        "[1/1/25, 1:00:00\u202fPM] Zach: " + LRM + "This message was deleted.",
    ]
    data = parse_chat(_write(tmp_path, lines))
    msgs = data["messages"]
    assert len(msgs) == 4
    for m in msgs:
        assert m["is_system"] is True, f"system line not flagged: {m['text']!r}"
        assert m["sender"] is None, "system event wrongly attributed to a member"
    # Real text is preserved, not deleted.
    assert "created this group" in msgs[0]["text"]


def test_real_message_mentioning_added_is_not_system(tmp_path):
    # A member message whose body merely CONTAINS a system-ish word (no leading
    # U+200E) stays a real member message.
    lines = ["[11/14/23, 9:24:00\u202fAM] Karim: Trades are what brings added fun"]
    data = parse_chat(_write(tmp_path, lines))
    m = data["messages"][0]
    assert m["is_system"] is False
    assert m["sender"] == "Karim"


def test_poll_is_member_message_not_system(tmp_path):
    # Polls are a real member action, NOT a system event: keep the sender and
    # surface a proper poll record (is_poll + parsed poll_data). The message
    # spans continuation lines (question + OPTION rows), which are appended.
    lines = [
        "[9/7/23, 6:04:52\u202fPM] Brent Boone: " + LRM + "POLL:",
        "Who is more likely to be sacko this year?",
        LRM + "OPTION: Matt (Chudders) (5 votes)",
        LRM + "OPTION: Blake (Kenobi) (2 votes)",
    ]
    data = parse_chat(_write(tmp_path, lines))
    assert len(data["messages"]) == 1
    m = data["messages"][0]
    assert m["is_system"] is False, "a poll must not be classified as system"
    assert m["sender"] == "Brent Boone", "poll must keep its member sender"
    assert m["is_poll"] is True
    assert m["poll_data"]["question"] == "Who is more likely to be sacko this year?"
    opts = m["poll_data"]["options"]
    assert {"text": "Matt (Chudders)", "votes": 5} in opts, opts
    assert {"text": "Blake (Kenobi)", "votes": 2} in opts, opts


def test_bidi_and_mention_isolates_stripped(tmp_path):
    # DEFECT D: LRM plus @mention directional isolates (U+2068/U+2069) must be
    # stripped from stored text.
    lines = ["[9/7/23, 6:00:00\u202fPM] Sacko: Surprised @\u2068Zach\u2069 didn't bid"]
    data = parse_chat(_write(tmp_path, lines))
    m = data["messages"][0]
    for ch in ("\u200e", "\u2068", "\u2069"):
        assert ch not in m["text"], f"bidi char {ch!r} leaked into text"
    assert m["text"] == "Surprised @Zach didn't bid"
    assert "Zach" in m["mentions"], "mention extraction broke after isolate strip"


def test_omitted_media_placeholder_is_not_system(tmp_path):
    # "image omitted" (no <attached:>) is real member media, not a system event.
    lines = ["[9/7/23, 6:00:00\u202fPM] Brent Boone: " + LRM + "image omitted"]
    data = parse_chat(_write(tmp_path, lines))
    m = data["messages"][0]
    assert m["is_system"] is False
    assert m["sender"] == "Brent Boone"
