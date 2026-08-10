# Pick Media (week ${WEEK})

For each `{{media:slot_id}}` declared in the edition's content JSON, choose
media: prefer the league's own catalog (real league photos and clips beat
stock GIFs), else GIPHY search via `scripts/resolve_media.py` (GIPHY
sometimes serves a canned junk batch; re-fetch rather than trusting one bad
set). Write selections to `media_picks.json` beside the content, resolve to
`media_cache.json`, and keep 2-4 slots per edition at most. Media punctuates;
it never carries.
