# Concept 03: The Playfield

> Generated 2026-04-10 by Creative Director synthesis.
> Status: CANDIDATE (not selected — comparison pending)

## 1. Name

**The Playfield.** A playing field. A force field. A field of data. The name works in three registers: the literal (a football field), the spatial (an open canvas), and the revelatory (a field that plays back to you). No "The Jailyard" in the title — the brand lives inside, not on top.

## 2. Core Identity

Twelve dots on a dark screen. That's the first impression. What looks like a loading state is actually the entire product — a gravitational map of your league where every interaction peels back another layer. The story isn't told. It's encountered. The Playfield replaces the scroll with space, the article with atmosphere, and the page with a single, evolving canvas that contains four years of your league's history in one view.

This is not a dashboard. Dashboards are for admitting you have a spreadsheet problem. This is not a visualization demo. Demos are for conferences, not Tuesday nights. The Playfield is a spatial narrative engine — a place where data, writing, rivalry, and trash talk exist as matter you can touch, pull, and orbit around. Think of it as Google Earth for your fantasy league: one surface, infinite depth, and the conviction that zooming in always reveals something you didn't expect.

**The secret:** it's deceptively simple at first glance. Twelve dots. No instructions. No "Welcome to your dashboard!" chrome. Just a dark field with breathing nodes. The sophistication is behind every interaction, not in front of it. You lean forward because it looks like there's more. There is.

## 3. Weekly Experience

**Tuesday, 9:00 PM — The Shift.**

The canvas you left last week transforms. Nodes migrate to new orbital positions. Connection lines redraw. The entire field rearranges over a 4-second animation. If your team climbed, you feel it — your node drifts inward, grows slightly, breathes slower (confidence). If you dropped, you feel that too — pushed toward the outer rings, node shrinking, pulse quickening. The Shift is the weekly reveal, visible to all twelve members simultaneously. No countdown timer, no locked content. You simply open the site and the field is different.

**The first 30 seconds:** You find your dot. You see where it moved. You see who's near you — who you're chasing, who's gaining on you. A faint line connects you to this week's opponent; it glows with the result. You already feel something before reading a single word.

**The next 5 minutes:** You tap your node. It blooms into a radial burst: your ranking blurb, your score, your top performers, a chat quote about you from the week. The writing lives here — not as an article you scroll through, but as fragments that orbit your team. Tap an opponent's node and see theirs. Tap the connection line between two teams and the rivalry card surfaces: all-time record, last meeting, the single most savage chat quote from their history. Tap the center of the field and the weekly essay unfolds as a full-screen overlay — the one piece of long-form writing, framed as the "Field Notes" for that week.

**What you tell the group chat:** "Bro tap your dot" or "look where they put you" or "click the line between us." Every sentence is an invitation to interact, not a link to share.

## 4. Season Arc

The canvas itself evolves. Not just the data — the visual language.

- **Weeks 1-4: Open Field.** Maximum spacing between nodes. Everything is possibility. Connection lines are thin, translucent. New teams to the league get a faint "incoming" animation. The field feels vast and unresolved.
- **Weeks 5-9: Gravity.** Nodes begin clustering. Winners pull toward center, losers drift outward. Connection lines thicken with each matchup played. Trade lines appear as distinct dashed arcs. The field is tightening. Rivalry connections start glowing based on intensity.
- **Weeks 10-13: Compression.** The orbital field physically shrinks. Playoff contenders are in a tight inner ring; eliminated teams grey out and drift to the margins. The visual density increases. Chat quotes become more frequent in the ambient layer. The field feels crowded, claustrophobic — because the season is.
- **Week 14 (Playoffs): The Bracket.** The canvas transforms. The orbital field collapses into a bracket structure, but the nodes retain their size, pulse, and connection history. Eliminated teams don't disappear — they become spectator nodes on the periphery, still showing their full-season trail.
- **Championship Week: The Ring.** Two nodes. Center of the field. Everything else is pushed to the outer darkness. The entire four-year history of both franchises plays as a continuous ambient loop behind the final matchup. The winner's node explodes into a supernova animation. The loser's fades to a memorial marker. Both are permanent.

## 5. Five Signature Features

### 1. The Field

The canvas itself. Twelve nodes in orbital positions determined by power ranking (center = #1, edge = #12), sized by point differential, colored by team identity. Nodes breathe — slow pulse for dominant teams, rapid pulse for volatile ones. This is the product. Everything else is what you discover inside it.

### 2. The Bloom

Tap any node and it blooms: a radial expansion revealing the team's week — ranking blurb (the full editorial paragraph), score, top performers, movement arrow, and one ambient chat quote. The writing isn't lost; it's spatialized. Twelve blooms, twelve personal letters. The editorial standard applies here identically. You're reading TO the owner, second person, conversational, roast-ready.

### 3. The Threads

Connection lines between every team pair. Thin by default. Hover or tap a thread and the rivalry card surfaces: all-time H2H record, Elo differential, trade history, and the single most relevant chat quote from their shared history. Threads thicken over the season as teams accumulate matchups. After four years, the thread between two rivals is visually unmistakable — a thick, hot line that practically vibrates.

### 4. The Rail

A timeline scrubber at the bottom of the canvas. Drag it and the entire field animates: nodes migrate, connections redraw, the season replays like a time-lapse. Drag across season boundaries and the field restructures for a different year. Four years of history in one continuous gesture. The Rail turns the Playfield from a weekly snapshot into a living archive. Release the scrubber at any point and you're looking at that exact week's state — tap any node and read that week's blurb.

### 5. Field Notes

The weekly essay — the long-form column — lives as a full-screen overlay triggered from the center of the field. A pulsing focal point at the canvas origin opens into "Field Notes: Week N." This is where long-form narrative lives. Unlike the Bloom blurbs (team-specific fragments), Field Notes is the panoramic view: the meta-narrative, the chaos summary, the connections between matchups that no single node can contain. The mailbag, comedy bits, and matchup picks live as sections within Field Notes. One tap in, one tap out. The writing quality is preserved; the delivery is spatial.

## 6. Design Language

- **Background:** True black (#000000) with a subtle radial gradient toward dark blue (#0a0a1a) at center — the field has depth
- **Nodes:** Team-colored with soft glow halos. Inner ring = warm tones (gold, amber), outer ring = cool tones (steel, slate). Champion nodes carry a permanent crown particle
- **Typography:** Geist Mono for data labels and stats. Newsreader for Field Notes essay text. System sans-serif for UI chrome
- **Connection lines:** SVG paths with variable stroke-width and opacity. Active matchup = bright, historical = muted
- **Ambient text:** Chat quotes drift across the field as low-opacity, slowly moving text fragments — readable if you focus, atmospheric if you don't. Never more than 3 visible simultaneously
- **Motion:** Physics-based spring animations for node movement. No easing curves — nodes settle like they have mass. The Shift animation uses staggered timing so nodes arrive at different moments. Zero infinite animations. All motion is state-transition or interaction-triggered
- **Sound:** Optional. A low ambient tone that shifts pitch based on which region of the field you're hovering. Off by default. Fantasy football doesn't need sound. But the option exists for the person who opens this at midnight

## 7. Shareability Engine

An interactive canvas can't be screenshotted. So The Playfield generates screenshots for you.

- **Field Snapshots:** A "Capture" button renders the current canvas state as a static 1200x630 PNG — your node highlighted, your rank, your bloom visible. Automatically composited with the week number and league branding. This is the Verdict Card equivalent: a frozen moment of the field with YOUR team's context.
- **Rivalry Cards:** Tap a thread, hit share. The rivalry card between two teams renders as an image: H2H record, Elo comparison, the chat quote, and both nodes with the thread between them. This is the thing you text to your rival.
- **The Weekly Shift GIF:** The 4-second Shift animation (last week's positions to this week's) auto-exports as a 5-second looping GIF/WebM. Post it in the group chat. Watch everyone find their dot moving.
- **Rank Receipt:** A minimalist text-image showing your ranking trajectory across the season: "Wk1: #7 → Wk2: #4 → Wk3: #2 → Wk4: #1 → Wk5: #1 → Wk6: #3." Simple. Devastating when someone falls.

## 8. History Experience

**Landing experience for a new visitor:** The field loads with current-week positions. The Rail is visible at the bottom, marked with season dividers (2022 | 2023 | 2024 | 2025). A subtle pulse on the Rail invites interaction. Dragging it all the way left starts the origin story: Week 1, 2022, twelve evenly-spaced nodes. Dragging forward, the visitor watches four years of league history unfold as continuous motion — teams rising, falling, trading, winning championships. Championship weeks trigger a brief supernova at the winner's node.

**"The Fossils"** — at any point on the Rail, tap a node and read the Bloom for that historical week. The archive isn't a separate page; it's the same field at a different time. History is always one drag away.

**Elo Trails:** Toggle an option and each node gains a trailing line showing its Elo path across the entire timeline. The field becomes a tangle of trajectories — beautiful as abstract art, meaningful as a franchise biography. The champion's trail glows.

## 9. Provocative Elements

- **YES:** Gravitational ranking (your position on the field IS your rank — no hiding from it). Public movement animations (everyone sees who fell). Ambient chat quotes (your words drift across the field for everyone). Rivalry thread intensity (the thickness of the line between you and your nemesis is visible to all 12 members). The loser's memorial marker after championship week.
- **NO:** Leaderboards or tables (the FIELD is the leaderboard). Commenting or reactions on the site (that's what the group chat is for). AI-generated banter between teams (the writing staff is the voice, not a chatbot). Gamification badges or achievements. Sound that auto-plays. Any feature that requires a login.

## 10. What We're NOT Building

Not a publication (that's The Clubhouse). Not a surveillance operation (that's The Yard). Not a dashboard with charts. Not a data visualization portfolio piece. Not an app that requires onboarding. Not a social network with profiles. Not a mobile-first swipe experience. Not a site that needs a "How to use" page. Not a product that looks impressive in a demo but has nothing to do on the second visit. The Playfield is a place you go to see your league — the same way you open Google Maps to see a city. It doesn't explain itself. It shows you where everything is.

## 11. Licensing Hook

"Every league is a solar system. Ours just has a map."

The Playfield is MORE licensable than a template site, not less. A traditional editorial site requires writing for every league — bespoke content, league-specific voice. The Playfield's core experience is data-driven: feed it Sleeper API data and it generates the orbital field, connection threads, Elo trails, and Shift animations automatically. The premium layer is the writing (Bloom blurbs, Field Notes), which the existing AI content pipeline produces from any league's data.

**Licensing model:** config.json (team colors, league name, Sleeper ID) + data pipeline (fetch_sleeper.py already league-agnostic) = functional Playfield in under an hour. Content pipeline (write-week, edit-week, render) = premium tier. The canvas visualizations are the free hook; the narrative engine is the paid moat.

**Why this scales:** The hardest part of licensing a content site is the content. The hardest part of licensing a visualization is the data mapping. The Playfield's data mapping is already solved (Sleeper API), and the content pipeline already produces league-agnostic output from any league's JSON. A new league plugs in their Sleeper ID. The Playfield draws itself. The editorial system writes the columns. The owner never touches code.

## Source Material

- 10 creative agent reports from Concept 01 + 7 from Concept 02 (cross-referenced)
- Original Playfield pitch from Data Artist agent (Concept 02 session)
- Research synthesis (`docs/v2-research-synthesis.md`)
- Content pipeline architecture (CLAUDE.md)
- Week 6 content JSON + Week 7 data JSON (representative data shapes)
- Editorial standard (`content/editorial-standard.md`)
- 392 matchups, 21K chat messages, 4 seasons of Elo data
