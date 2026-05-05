# MrBeast principles — distilled for chart-race Shorts

Distilled from the 1-hour MrBeast advice compilation at
`mrbeast_advice_transscript.md`. Translated to the chart-race short-form
context (no B-cam cuts, no live filming — but the underlying audience
psychology applies cleanly to data races).

> **Source quotes are paraphrased, not invented.** Every principle below
> traces to something MrBeast actually said in the transcript.

---

## How to apply this file

When a video skill invokes you, you are deciding one of three things:

1. **Pick a video idea** — given `ideas.md` (world) or a stat domain (sports),
   choose ONE that scores highest against the rubric below.
2. **Curate big-mover events** — given a candidate list from
   `cache/big_movers.json`, set `keep:true` on the events that score highest.
3. **Draft title + hook** — given the chosen dataset, propose a title and the
   first-3-second narration line that scores highest.

Score candidates 1–10 on the rubric. **Pick the top one and state your
reasoning in 1–2 sentences** so the user can sanity-check at the
pre-upload checkpoint.

A candidate must score **≥7 on Hook strength** and **≥6 average across the
rest** to qualify. Anything below that — surface to the user, don't ship.

---

## The rubric

### 1. Hook strength (first 3 seconds) — A SIMPLE QUESTION, 10-YEAR-OLD LANGUAGE
Does the opening line ask a short, simple question about the topic — in
words a 10-year-old uses on the playground?

- **Why:** "Tied up an FBI agent, $100k in this bag, here's a knife, good
  luck" gives you everything in 7 seconds — no wasted words, short, concise,
  tension. MrBeast says the first 10 seconds are the most undervalued part
  of the video. For a chart-race Short the failure mode is a CONFUSED
  viewer — and confused viewers swipe instantly. The fix is not "explain
  the chart". The fix is to ask a question about the TOPIC so plainly
  that a 10-year-old understands the stakes immediately. The chart on
  screen will answer the question.
- **How to apply (script):** Beat 1 is a short SIMPLE QUESTION about the
  topic, ≤10 words, in plain everyday language. Forbidden words in the
  hook: "bars", "chart", "race", "leaderboard", "data", "ranking",
  "graph", "stats". Just ask about the topic itself.
  ✅ "Which country has the most tourists?"
  ✅ "Which country spends the most money on its army?"
  ✅ "Which country has put the most CO2 into the air, ever?"
  ❌ "ok so each bar is a country racing tourist arrivals" (mentions
     bars, sounds like a label, not a question)
  ❌ "tell me which country runs tourism" (vague, viewer guesses what
     "runs tourism" means)
  ❌ "Today we're looking at patent data from the World Bank." (formal,
     no stakes, list intro)
- **10-year-old language across the whole script.** Concrete > abstract.
  "Money" not "expenditure". "Got hit hard" not "experienced a sharp
  decline". Two clauses per sentence max.
- **How to apply (idea selection):** If you can't phrase the dataset's
  topic as a 10-word question a 10-year-old understands, the dataset is
  too abstract for a Short — pick another.

### 2. Match-then-exceed expectations
Does the video deliver what the title/thumbnail promises within seconds, then
go beyond?

- **Why:** "If you click on a video where the title is 'Tether is a scam'
  and the first words are about anything else, you're like 'this isn't what
  I clicked on.'" Match the promise within the first 3 seconds, then exceed
  it.
- **How to apply (title↔hook coherence):** The title and the opening
  narration line must share a noun and a stakes-word. If the title says
  "Patents" and the opener says "applications," that's fine. If the title
  says "Patents" and the opener says "Today's data," that's a fail.
- **How to apply (idea selection):** Avoid datasets where the headline
  promise (e.g., "who's #1 in X") is undermined by a boring middle.

### 3. Extreme > generic
Is the framing extreme/specific enough to be unmissable?

- **Why:** "First to finish a race wins $100k" is generic — it's been done.
  "First to climb a mountain wins $100k" is extreme — the thumbnail of
  someone climbing a mountain is adrenaline. Same for titles: "How to go
  viral" is too weak. "If you don't click, you can't sleep tonight" is the
  bar.
- **How to apply (idea selection):** Score datasets on whether the climax
  is *visually extreme* or just numerically different. CO2 accumulated
  (US dwarfs everyone for decades, then China overtakes) > GDP totals
  (China's rise is huge but slow). Patent applications (Japan→China handoff
  in the 2010s) > Trade balances (rotation without drama).
- **How to apply (titles):** Prefer concrete extremes over vague comparatives.
  ✅ "China overtook the US in patents in 2011" ❌ "Patent leaders over time."

### 4. Visual legibility / no dull moments
Does the race have visible motion at all phases of the timeframe?

- **Why:** "Cut every dull moment. If I'm even slightly bored, cut it. If
  it's not 'wow' the whole time, don't upload." For data races, dullness =
  flat sections where rank doesn't change.
- **How to apply (preview check):** After preview frames render, if two of
  three frames have identical top-N composition, the dataset has dead air.
  Surface it. The fix is either a tighter timeframe (skip the flat early
  years) or a different dataset.
- **How to apply (idea selection):** Reject datasets where the entire arc
  is "country A leads forever, then country B leads forever." Need ≥2 rank
  changes in the visible top-N within the timeframe.

### 5. Payoff at end
Does the climax give the viewer a reason to stay through the whole race?

- **Why:** "Last to leave the circle wins $10k — even if there's a low
  moment halfway, you watch to the end because you want to see who wins."
  For chart races, the equivalent is: does the final ranking surprise, or
  resolve a tension set up in the hook?
- **How to apply (idea selection):** Prefer datasets where the *end* of the
  timeframe is the dramatic moment (China's 2023 patent dominance > a
  dataset that peaks in 1995 then flatlines).
- **How to apply (script ending):** The ending beat must reference the
  hook's promise. If the hook said "watch the year China flipped Japan,"
  the ending must explicitly land on that flip.

### 6. Familiarity + surprise
Does the topic touch something the audience already half-knows, with a twist
they don't expect?

- **Why:** From `ideas.md` line 9 + reinforced by transcript ("study what
  spawns in your head from new inputs"). Audience needs an anchor —
  recognizable countries, eras, events — but the surprise is what makes
  them share.
- **How to apply (idea selection):** Score higher if the dataset contains
  at least one recognizable inflection point (USSR collapse, 2008, COVID
  cliff, China's WTO entry, oil shocks, India's 2023 population crossover).
- **How to apply (big-mover curation):** Among `cache/big_movers.json`
  candidates, prefer events tied to recognizable history. A 1987 spike in
  some indicator that "just happened" scores lower than a 1991 USSR-related
  collapse, even if the magnitude is similar.

### 7. Replay/share value
Is there a screenshot or one-liner from the climax worth sending to a
friend?

- **Why:** "What you want is people to watch 10 videos, not 1, and need a
  week to recharge because each one was so 'holy crap'." For Shorts, the
  equivalent is: does the viewer text the climax to someone?
- **How to apply (idea selection):** Visualize the climax frame in your
  head. Is it a screenshot-worthy moment? "China at #1 with 2x the next
  country" is shareable. "Top 5 countries within 3% of each other" is not.

---

## Hook patterns (use these literal templates)

The default hook is ONE simple question naming the topic, in plain
playground-level English. Optionally a short tease follows. Question
patterns:

- **"Which country has the most ___?"** — works for population,
  tourists, internet users, patents, etc.
- **"Which country spends the most on ___?"** — military, healthcare,
  education, R&D.
- **"Which country has put the most ___ into the world, ever?"** —
  cumulative CO2, cumulative aid given.
- **"Which country grew the fastest?"** — works for any sustained-rise
  story.

Optional tease patterns (after the question, ≤8 words). These are NOT
required — a clean question alone is fine.

- **Stakes-flip:** `[Country A] crushed [Country B] in [metric] — watch the
  year it flipped.`
- **Climax-tease:** `Only one country has ever held #1 in [metric] for
  [N] years straight. Watch what dethrones it.`
- **Counterfactual:** `You'd think [intuitive answer] leads in [metric].
  You'd be wrong.`
- **Era-collapse:** `[Era-defining event] changed [metric] forever — here's
  the receipt.`
- **Number-shock:** `[Country] makes [N×] more [metric] than the next 10
  countries combined.`

Avoid: "Today we look at…", "Have you ever wondered…", "The data shows…".
These are MrBeast's "you have 20 seconds before you meet expectations" trap.

---

## Title patterns (use for `video_title` in config)

Same logic: extreme, concrete, specific. Keep ≤45 chars for layout safety
(see `layout_check.md`).

- **Verbed comparison:** "China Crushed Japan in Patents"
- **Number-led shock:** "1 Country, 30% of All Patents"
- **Era-anchored:** "How USSR's Collapse Reshaped Reserves"
- **Question with implied answer:** "Which Country Files the Most Patents?"
  (the existing default — fine but mid; only use when the dataset's climax
  *is* the answer reveal)

Avoid generic descriptors ("Patent Trends 1980–2023"). MrBeast: "How to go
viral" is too weak — you need something where if they don't click, they
can't sleep.

---

## Big-mover curation rubric

When `cache/big_movers.json` is generated, score each candidate event 1–10
on:

1. **Recognizability (0–4)** — does the year/entity tie to a real
   historical event the audience knows? (USSR 1991, 2008 crisis, COVID
   2020, etc.)
2. **Magnitude (0–3)** — how dramatic is the rank change or rate spike?
3. **Spacing (0–3)** — does keeping this event leave a gap of ≥3 years to
   the next kept event? Density of events kills pacing.

Set `keep:true` on the **top 3–6 events** for a Short. More than 6 = the
spotlights step on each other. Fewer than 3 = the middle of the video has
dull air (violates Rubric #4).

---

## Anti-patterns — never do these

- **No "today we look at…" openers.** Match expectations within 3 seconds.
- **No dull middles.** If preview frames show two identical top-Ns, kill
  the idea or tighten the timeframe.
- **No P-jokes / crude humor.** Per transcript: drops attention ~5%.
- **No more than one knob change per layout retry.** (See `layout_check.md`.)
- **No vague titles.** Concrete > abstract. Numbered > qualitative.
- **No milking a format.** If the previous 2 world-stats videos were both
  "money & power" datasets, pick from a different `ideas.md` section. (MrBeast:
  "don't milk a series too hard, keep it fresh.")
- **No copy-pasting an arc.** If a previously-shipped video already used
  the China-rise-post-2001 narrative, the next idea should center a
  different inflection point.

---

## Per-channel vibe (v1 — same principles, different tone presets)

The principles above apply to both channels equally. The only thing that
differs in v1 is voice/tone in the narration config:

- **World-stats** (`config.json::render.narration.tone`): "hype friend
  watching with you, casual and loud, slang OK, no suit-and-tie words."
  Already configured this way. Suits geopolitics, demographics, climate.
- **Sports-stats**: same tone profile is fine for v1. Sports audience is
  more forgiving of slang and "GOAT debate" energy than world-stats. When
  the sports CLI exposes narration (see CLAUDE.md::Later), revisit this.

Audience-data tuning is deferred per `CLAUDE.md` §28 until ≥30 videos with
retention exist.

---

## When in doubt

The transcript's most repeated line: **"It's much easier to get 5 million
views on one video than 100,000 views on 50 videos."** If you're scoring
two ideas and one is "safe and shippable" and the other is "extreme and
risky," pick extreme. The risk of a dull video is worse than the risk of
a wild one.
