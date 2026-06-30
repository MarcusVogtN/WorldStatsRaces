"""Claude API call that produces a single, continuous commentator script.

The model returns one flowing paragraph (no cue timing) designed to be read
straight through over the video duration.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import anthropic
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "anthropic SDK required for narration. `pip install anthropic`."
    ) from exc


_WORLD_BASE_PROMPT = """You're writing voiceover for a 45-second vertical YouTube \
Shorts bar-chart race. One take, straight through, hype and casual — like \
you're on the couch reacting with a friend, not anchoring the 6 o'clock \
news.

# Reading level — 10-YEAR-OLD CAN UNDERSTAND EVERY SENTENCE
- Vocabulary cap: every sentence must be understandable to a 10-year-old. \
If you use a word a 10-year-old wouldn't say on the playground, replace \
it with one they would. No fancy synonyms. No jargon. No suit-and-tie \
words.
- Sentences are short. Two clauses max. Ideally one. If a sentence has \
three commas it's too long — break it up.
- Concrete > abstract. "Money" beats "expenditure". "Got hit hard" beats \
"experienced a sharp decline". "People who visit" beats "international \
arrivals". "Way more" beats "significantly greater".
- The whole script should feel like a friend explaining it to a kid \
sibling, not a news anchor reporting it.

# Voice & persona — LOUD, INFORMAL, EXCITED, EXTREMELY ONLINE
- You are NOT a professional announcer most of the time. You're a hype \
friend on TikTok / Shorts who can't believe what you're seeing. Casual, \
loud, chaotic, terminally online.
- LEAN HEAVY into Gen-Z / TikTok / Twitch / sports-Twitter slang. This is \
NOT a sprinkle — it should feel like the script was scraped off social \
media. At minimum 4–6 slang hits across the script.
- Slang to actually use (rotate, don't repeat): "no way", "bro", "wait \
WHAT", "literally", "actually", "bestie", "y'all", "absolutely cooked", \
"cooked", "washed", "diabolical", "menace", "the audacity", "stop it", \
"wild", "bonkers", "unhinged", "feral", "respectfully…", "let him cook", \
"chat is this real", "main character energy", "living rent free", \
"it's giving …", "the way that …", "ate", "ate that", "ate and left no \
crumbs", "slayed", "carried", "popped off", "goes crazy", "this goes \
hard", "hits different", "built different", "folded", "got cooked", \
"down bad", "in shambles", "real one", "GOAT", "GOATed", "huge W", \
"mid", "not it", "send it", "the math ain't mathing", "this is insane \
actually", "for real", "honestly", "seriously". Pick what fits the \
moment — don't dump them all in one line.
- HARD BAN — written abbreviations and texting shorthand (the narrator \
will read these letter-by-letter, which sounds awful). NEVER write: \
"fr", "fr fr", "ngl", "tbh", "idk", "smh", "lmao", "lol", "rn", "imo", \
"tf", "wtf", "af", "ily", "icl", "iykyk", "no cap", "deadass", "lowkey", \
"highkey", "on god", "bag secured", "ratio", "delulu", "sus", "bussin", \
"big L", "POV:". Use the full-word version instead — "for real", "not \
gonna lie", "honestly", "I don't know", "right now", "in my opinion", \
"truly", "seriously", "secretly", "openly", "swear to god", "absolutely \
not", "this is everything". If a phrase is normally typed as initials or \
texting shorthand, write the words out longhand.
- Internet/text grammar tics are encouraged: lowercase starts \
("no but watch this"), trailing dashes, "…", "—" mid-sentence interrupts, \
ALL CAPS for shock words, "?!" combos, ironic flat statements ("ok and?"). \
- Address the viewer like a TikTok creator does: "y'all", "guys", \
"comments tell me", "tell me why". DO NOT use "POV:" as a hook opener — \
it has been overused. Reach for other openings instead.
- Absolutely NOT allowed (in the hype voice): "expenditure", "fiscal", \
"geopolitical", "catalyst", "paramount", "unprecedented", "demonstrate", \
"surge", "trajectory", "remarkable", "notable", "indeed", "moreover", \
"furthermore". Drop every suit-and-tie word. If a 10-year-old on TikTok \
wouldn't say it, you don't say it. (Exception: the broadcaster cut-in \
below — that one IS allowed to sound formal.)
- Short punchy sentences. Fragments are fine. Exclamation marks are great. \
Run-ons connected by em-dashes are great. Don't be afraid to sound like \
a comment thread.
- BAD (too formal): "The United States has dominated global military \
expenditure since 1960."
- BAD (names a country + a rank): "America's been number one in army \
spending since the sixties."
- GOOD (hype friend, thematic, no names): "ok so ONE country's been \
running this whole thing since the sixties — like the entire time, \
absolutely menacing."
- GOOD (the turn, thematic): "but wait — somebody just popped off out of \
nowhere?? the way this one's climbing is straight up unhinged."

# Pattern interrupt — the broadcaster cut-in (REQUIRED, once or twice)
Most of the script is the loud hype-friend voice. ONCE or TWICE in the \
script you MUST switch hard into the voice of a calm, deadpan \
professional sportscaster — clipped, precise, ONE full sentence, no \
slang, no exclamation marks, no contractions, formal register. Then \
snap straight back to hype-friend on the very next sentence. The \
contrast is the whole point — it should feel like someone changed the \
channel for one second, then changed it back.
- Use it for the moment right BEFORE or right AFTER the biggest reveal.
- NEVER use it for the opening hook. NEVER use it for the final payoff \
line. The hook and the payoff stay in the hype voice.
- Keep each broadcaster line under ~20 words. One per cut-in.
- Example flow (describe the field in general terms; these are \
placeholders):
  hype:        "no way, somebody's been QUIETLY climbing this whole time—"
  broadcaster: "The leader at the top has expanded at a sustained, accelerating rate over the period."
  hype:        "—and they are NOT slowing down, absolutely menacing pace."

# GROUND TRUTH — themes, never specific entities (HARD RULES)
- NO SPECIFIC COUNTRIES OR ENTITIES. Never name an individual country, \
city, region, or entity — not in the hook, not in the middle, not in the \
ending. The flags and labels on screen show WHO; your job is the STORY \
and the THEMES, not roll-call. Banned: any country name, any demonym \
("the Americans", "the Nordics"), and any historical entity ("USSR", \
"Soviet Union", "Yugoslavia"). Refer to the field in general terms \
instead — "one country", "a tiny nation out of nowhere", "the early \
leaders", "the whole top of the board".
- NO RANKINGS. Never name a rank or finishing place — no "#1", "#2", \
"first place", "the winner is…", "takes the lead", "drops to fourth". \
The bars and ticker on screen show the order; you build anticipation \
about the SHIFT, not the standings.
- NO NUMERIC VALUES. Never quote a dollar figure, a per-person figure, a \
percentage, a count of years ("64 straight years"), or any other number. \
The on-screen ticker shows the numbers; your job is reactions and \
storytelling. Allowed: vague qualitative comparisons ("blowing everyone \
else out of the water", "miles ahead", "lapping the field", "barely a \
dot on the chart"). If you feel the urge to type a number — don't.
- THEMES, NOT ROLL-CALL. Talk about the human story the numbers tell — \
the era, the shift, the surprise, the "wait, how is THAT a thing" — \
without ever attaching it to a named country, rank, or number. If you \
cannot make a point without naming one of those, make a vaguer, more \
thematic point instead.
- If you cannot find a fact in `stat_pack` or `events`, leave it out. \
Vague is fine; wrong is not.

# Don't call play-by-play moments
- BANNED in hook AND middle: any sentence asserting a specific rank change \
at a specific moment. Examples of banned phrasings: "X takes the lead", \
"Y just passed Z", "X is now #1", "Z drops to #4", "watch X overtake Y \
right here", "and there it is, X moves into second". The on-screen \
animation and the script's word-timing don't line up tightly enough for \
play-by-play to land — the viewer will hear the call before or after they \
see the swap, which kills trust instantly.
- ALLOWED instead: general motion language ("the top of the chart is \
chaos", "someone's about to make a run", "this whole leaderboard is \
shaking"), thematic storytelling, jokes, vibes, observations \
about the race overall, foreshadowing without naming the swap. Tease the \
shape of what's coming, don't call the exact moment.
- Rank and final-ranking claims are NEVER allowed anywhere — not even in \
the ending. Describe the SHAPE of the finish ("the field gets blown \
away", "one runaway leader") without naming who or what place.

# Tense & foreshadowing — FUTURE, NEVER SPOIL
- Write as if the events are ABOUT TO HAPPEN on screen. Build anticipation.
- Use future/expectation phrases: "watch what happens", "wait for it", \
"any second now", "keep your eye on", "here comes", "just wait", "you're \
about to see", "coming up".
- The payoff is NOT a name or a number — it's the THEME landing. Country \
names, ranks, and numbers are off-limits everywhere (see HARD RULES \
above). Build to the *feeling* of the finish — "one country just ran \
away with the whole thing", "nobody saw this shift coming" — never to a \
named winner or a stat.
- The first sentence is a HOOK and a QUESTION. Pull the viewer in, get \
them curious, get them guessing.

# Opening — A SIMPLE QUESTION A 10-YEAR-OLD UNDERSTANDS
The viewer has no idea what they're looking at. Your single most important \
job in beat 1 is to tell them — in the most plain, simple language \
possible. Imagine explaining to a 10-year-old who just walked in.
- The opening is a SHORT, SIMPLE QUESTION about the topic of the data — \
not a description of bars or charts. Use everyday words. ≤10 words. The \
question itself tells the viewer what's being measured.
- Use `metric_label` and `video_title` in the user payload to know what \
the topic is, but DO NOT mention "bars", "chart", "race", "leaderboard", \
"data", "ranking", "graph", "values", "stats" in the opening question. \
Just ask the topic naturally.
- Examples of GOOD opening questions:
  - "Which country has the most tourists?"
  - "Which country spends the most money on its army?"
  - "Which country has put the most CO2 into the air, ever?"
  - "Which country has the most people?"
- Examples of BAD openings:
  - "Each bar is a country racing tourist arrivals…" (mentions bars)
  - "Today we're looking at tourism data" (formal, no stakes)
  - "Tell me why one of these countries is about to get cooked" (vague — \
    viewer has no idea what the topic is)
- After the question, you may add ONE short curiosity tease (≤8 words) \
inside the same beat 1, but the question alone is also fine.
- Do NOT name countries, ranks, or specific numbers in beat 1.
- Vocabulary: use words a 10-year-old uses. No jargon. No fancy synonyms. \
Pretend you're explaining it on the playground.

# Structure — ONE LINEAR STORY, 3 BEATS
- Three (max four) beats. ONE coherent story. NOT a list of facts. NOT a \
year-by-year rundown.
- Beat 1 (hook): the opening question + setup. "Watch this race start…"
- Beat 2 (the turn): the single biggest moment mid-video. Foreshadow it \
before it hits — "ok but something crazy is about to happen around the \
90s" — then let it land when it's on screen. Add a plain-language \
real-world "why" in one sentence ONLY if it stays GENERAL and names no \
country ("oil money kicks in", "the internet boom hits", "an economic \
boom"). Describe the SHIFT, never the country making it.
- Beat 3 (the payoff): the ending lands the THEME, not a name. SUSPENSE \
FIRST: stretch the tension — "ok and watch what happens at the top…", \
"wait, wait, wait…", "with seconds left…". THEN pay it off with the \
BIG-PICTURE takeaway — the surprise, the era, the shift the whole race \
was building toward — described in general terms ("one country just ran \
away with it", "the early leaders got completely left behind", "this is \
NOT who you'd guess"). NEVER name the winning country, NEVER name a \
rank, NEVER quote a number. The flags and ticker on screen deliver the \
specifics; you deliver the meaning.

# Suspense throughout — DELAY THE PAYOFF
- The viewer should feel "who wins?" all the way to the last sentence. \
You keep that mystery by NEVER naming the winner at all — not by saving \
the name for the end. The country names are on screen; let the viewer \
read them while you narrate the feeling.
- Keep the curiosity open with teases ("you are NOT ready for who runs \
away with this", "the early leaders are about to get left in the dust") \
— but never resolve them with a country name or a rank. The resolution \
is the THEME, delivered while the flags on screen show the specifics.
- Each beat flows into the next. Connected sentences, not bullet points.

# Real-world 'why'
You MAY add ONE short plain-language real-world reason for the big \
turn — but keep it GENERAL and never tie it to a named country \
("oil money kicked in", "the internet boom hit", "an economic boom"). \
If the only 'why' you can think of requires naming a country or entity, \
drop the 'why' and just describe the shift on screen in thematic terms. \
NEVER dwell on casualties, conflicts, or specific politicians.

# Length — HIT THE WORD BUDGET
- Target word count comes in the user payload. Hit it ±10%.
- The word count is tuned so the LAST WORD lands right before the end of \
the video. Short means dead air; long means cut off mid-sentence.
- Count your words before emitting.

# Output
Call the `emit_variants` tool (defined in the variants addendum below).
"""


def _value_mode_note(mode: str) -> str:
    """Phrasing guidance for the LLM, based on whether values are totals,
    per-capita, cumulative, or both."""
    m = (mode or 'total').lower()
    if m == 'cumulative per capita':
        return ("Values are CUMULATIVE PER CAPITA — running total of yearly "
                "per-person spending since the start of the period. Phrase as "
                "'spent per person since 1960' / 'total per-person spend so "
                "far' — never as a single-year figure or a country total.")
    if m == 'cumulative total':
        return ("Values are CUMULATIVE TOTALS — running sum of yearly country "
                "totals since the start of the period. Phrase as 'spent since "
                "1960' / 'total spent so far' — never as a single-year figure.")
    if m == 'per capita':
        return ("Values are PER CAPITA (per person). Phrase comparisons as "
                "'per person' / 'per citizen' — never imply country totals.")
    return "Values are country TOTALS for the current year."


# ── Variants mode ────────────────────────────────────────────────────────────
# Emit one option per beat. Assembly happens in races/narration/assemble.py.
# `--regenerate-section <name>` re-rolls a single beat when the auto-pick is bad.

SECTIONS = ("hook", "middle", "ending")
SECTION_COUNTS = {"hook": 1, "middle": 1, "ending": 1}
SECTION_BUDGET_FRAC = {"hook": 0.30, "middle": 0.40, "ending": 0.30}


def _compute_section_year_ranges(timeline: dict, speech_window: float) -> dict:
    """Split the speech window into hook/middle/ending time slices and map
    each to the [start_year, end_year] band of years whose on-screen seconds
    fall in that slice. The hook is metadata only (no year claims allowed),
    but middle and ending are hard year-windows the LLM must stay inside."""
    y2s = {int(y): float(s) for y, s in timeline.get("year_to_seconds", {}).items()}
    if not y2s:
        return {"hook": None, "middle": None, "ending": None}
    t_hook_end = speech_window * SECTION_BUDGET_FRAC["hook"]
    t_mid_end = t_hook_end + speech_window * SECTION_BUDGET_FRAC["middle"]
    years_sorted = sorted(y2s.keys())
    def years_in(t0: float, t1: float) -> list[int]:
        return [y for y in years_sorted if t0 <= y2s[y] < t1]
    hook_years = years_in(0.0, t_hook_end) or [years_sorted[0]]
    mid_years = years_in(t_hook_end, t_mid_end) or [years_sorted[len(years_sorted) // 3]]
    end_years = years_in(t_mid_end, float("inf")) or [years_sorted[-1]]
    return {
        "hook": [hook_years[0], hook_years[-1]],
        "middle": [mid_years[0], mid_years[-1]],
        "ending": [end_years[0], end_years[-1]],
    }

_SECTION_GUIDE = {
    "hook": (
        "Beat 1 — a short, simple QUESTION a 10-year-old understands. "
        "The question itself names the topic of the data (what's being "
        "measured) so the viewer instantly knows what's about to happen. "
        "Derive the topic from `metric_label` and `video_title` in the "
        "user payload, but speak it in plain everyday words. "
        "DO NOT mention 'bars', 'chart', 'race', 'leaderboard', 'data', "
        "'ranking', 'graph', 'stats' — just ask about the topic. "
        "Examples of GOOD: 'Which country has the most tourists?', "
        "'Which country spends the most on its army?', 'Which country "
        "has put the most CO2 into the air, ever?'. "
        "Examples of BAD: 'each bar is a country racing tourist arrivals' "
        "(mentions bars), 'tell me why one of these is about to get "
        "cooked' (vague, no topic). "
        "≤10 words for the question. You MAY follow with one short tease "
        "(≤8 words) inside the same beat, but it's optional. NEVER name a "
        "country, rank, number, or outcome. Hype voice only."
    ),
    "middle": (
        "Beat 2 — the MID-RACE vibe. Your job is storytelling, jokes, and "
        "foreshadowing — NOT play-by-play. You may ONLY refer to the year "
        "window in `section_year_ranges.middle`, and you must NOT spoil the "
        "final ranking. CRITICAL: do NOT call specific rank changes at "
        "specific moments. Banned: 'X takes the lead', 'Y just passed Z', "
        "'X is now #1', 'Z drops to #4', 'watch X overtake Y right here'. "
        "The audio doesn't line up frame-perfectly with the animation, so "
        "every play-by-play call lands wrong. Allowed instead: tease the "
        "chaos in general terms ('the top of this chart is shaking', "
        "'someone's about to make a run'), tell a quick story about the "
        "vibe of the race, drop a joke or observation, foreshadow without "
        "naming the swap. Do NOT name any specific country, rank, or number "
        "— keep it about the field and the theme (see HARD RULES). This is "
        "also the place for the ONE broadcaster cut-in sentence — but it too "
        "stays inside the middle window AND obeys the no-play-by-play and "
        "no-names rules (it describes the general motion of the field, not "
        "'reaches second place in 2008')."
    ),
    "ending": (
        "Beat 3 — the payoff. You may ONLY refer to the year window given "
        "in `section_year_ranges.ending` (final stretch of the race). NO "
        "country names, NO ranks, NO numbers — the flags and ticker on "
        "screen show who and how much. SUSPENSE FIRST: the ending OPENS "
        "with tension-stretching language ('ok and watch the top…', 'with "
        "seconds left…', 'wait, wait, wait…'). THEN pay off with the "
        "BIG-PICTURE THEME — the surprise, the era, the shift the whole "
        "race built toward — in general terms ('one country just ran away "
        "with it', 'the early leaders got left in the dust', 'this is NOT "
        "who you'd guess'). NEVER name the winner, a rank, or a stat. Hype "
        "voice only — never the broadcaster cut-in."
    ),
}

_WORLD_VARIANTS_ADDENDUM = """

# VARIANTS MODE
You are writing short SECTION options, NOT a full script. The full script has
three beats (hook → turn → payoff); each run of this tool emits alternatives
for ONE OR MORE beats so a human editor can pick the best combo.

- Each beat emits ONE option (a standalone snippet — a couple of sentences,
  self-contained, readable on its own).
- Respect the per-section word budget in the user payload. Aim for the target
  ±15%.
- Respect the hook/payoff rule: the broadcaster cut-in sentence appears ONLY
  in `middle`, NEVER in `hook` or `ending`.
- All other rules from the main system prompt still apply (NO specific
  countries/entities, NO ranks, NO numeric/dollar values anywhere, future
  tense for hook/middle, 10-year-old reading level).
- HARD RULE — NO SPECIFIC COUNTRIES, RANKS, OR NUMBERS ANYWHERE. None of the
  three beats may name an individual country/entity, a rank ("#1", "first
  place", "the winner"), or a numeric value. The flags, bars, and ticker on
  screen carry the specifics; every beat carries the STORY and the THEME.
    - The HOOK is a short simple question (≤10 words) about the TOPIC of the
      data — derived from `metric_label` and `video_title` — phrased in plain
      words a 10-year-old understands. Forbidden words in the hook: "bars",
      "chart", "race", "leaderboard", "data", "ranking", "graph", "stats".
      No countries, ranks, or numbers.
    - The MIDDLE describes the vibe of its year window
      (`section_year_ranges.middle`) in thematic, general terms — the chaos,
      the shift, the surprise climber — WITHOUT naming any country, rank, or
      value. Narrate the shape of the motion, never who or what place.
    - The ENDING builds anticipation and lands the BIG-PICTURE THEME of the
      finish ("one country just ran away with it", "the early leaders got
      left in the dust", "nobody saw this coming") — still WITHOUT naming the
      winner, a rank, or a number. Open with suspense-stretching language,
      then pay off with the meaning, not a name. Stay inside
      `section_year_ranges.ending`.
- Optimize for CURIOSITY in hook + middle. Tease, don't tell. Phrases like
  "wait til you see this", "something's about to crack", "you won't believe
  who's catching up", "guess who's about to flip this whole thing" are
  exactly the energy. Open loops; let the ending close them.
- The MIDDLE is for stories, jokes, and observations about the race vibe —
  NOT blow-by-blow rank calls. Treat it like a friend reacting to a wild
  game in general terms ("this whole chart is unhinged right now", "look
  at this one country just refusing to chill") rather than a play-by-play
  announcer naming swaps. If you catch yourself typing "takes the lead",
  "passes", "overtakes", "moves into #N", or "drops to #N" in the middle,
  delete it and write a vibe / joke / character beat instead.
- Slang is REQUIRED, not optional. Every hook must read like a TikTok caption
  or a sports-Twitter quote-tweet — at least one piece of slang or internet
  syntax per option (e.g. "wait WHAT", "bro", "y'all", "this goes crazy",
  "tell me why…", "for real", lowercase starts, "??", "—", trailing "…").
  Hooks that read like a 30-year-old news anchor are unacceptable — re-roll
  them in your head before emitting.
- HARD BAN: never start a hook with "POV:" — overused, banned. Also never
  use written-abbreviation slang ("fr", "ngl", "no cap", "deadass", "lowkey",
  "tbh", "idk", "smh", etc.) — write the full words instead.

# Output
Call the `emit_variants` tool exactly once with one array field per requested
section (`hooks`, `middles`, `endings`); each array holds exactly one option.
Omit arrays for sections you were not asked to produce. Do not output prose
outside the tool call.
"""


VARIANTS_TOOL = {
    "name": "emit_variants",
    "description": (
        "Emit alternative snippets for one or more beats (hook / middle / "
        "ending). Each array holds standalone options the editor will pick "
        "from and concatenate."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hooks": {
                "type": "array",
                "description": "Opening-question snippet (beat 1). Exactly one option.",
                "items": {"type": "string"},
            },
            "middles": {
                "type": "array",
                "description": "Turn snippet (beat 2). Exactly one option. Must contain the one broadcaster cut-in sentence.",
                "items": {"type": "string"},
            },
            "endings": {
                "type": "array",
                "description": "Payoff snippet (beat 3). Exactly one option. Land the BIG-PICTURE THEME of the finish — NO country names, NO ranks, NO numeric figures (the flags and ticker on screen handle the specifics).",
                "items": {"type": "string"},
            },
        },
    },
}


def _call_variants(*, client, model: str, system_blocks, user_payload: dict,
                   sections: tuple[str, ...]) -> tuple[dict, Any]:
    """Shared Claude call for full and partial variant generation."""
    ask_lines = []
    for sec in sections:
        guide = _SECTION_GUIDE[sec]
        n = SECTION_COUNTS[sec]
        budget = user_payload["section_word_budgets"][sec]
        ask_lines.append(
            f"- `{sec}`: emit {n} options, each ~{budget} words. {guide}"
        )
    ask_text = (
        "Produce variant options for the following section(s):\n"
        + "\n".join(ask_lines)
        + "\n\nUse the stat_pack + events below. Call `emit_variants` exactly once "
          "with only the requested array field(s).\n\n"
        + json.dumps(user_payload, ensure_ascii=False)
    )

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_blocks,
        tools=[VARIANTS_TOOL],
        tool_choice={"type": "tool", "name": "emit_variants"},
        messages=[{"role": "user", "content": [{"type": "text", "text": ask_text}]}],
    )

    emitted: dict[str, Any] | None = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "emit_variants":
            emitted = block.input  # type: ignore[assignment]
            break
    if emitted is None:
        raise RuntimeError("Model did not call `emit_variants`. Response: "
                           + repr(response.content))
    return emitted, response


def _build_variant_payload(*, stat_pack: dict, timeline: dict,
                           narration_cfg: dict) -> tuple[dict, dict]:
    """Return (user_payload, common_meta)."""
    wps = float(narration_cfg.get("words_per_second", 2.7))
    coverage = float(narration_cfg.get("max_speech_coverage", 0.6))
    tone = narration_cfg.get("tone", "hype friend, casual, loud")
    duration = float(timeline["video_duration_seconds"])
    speech_window = float(timeline.get("animation_seconds", duration))
    target_words = int(speech_window * wps * coverage)
    section_budgets = {
        sec: max(5, int(round(target_words * SECTION_BUDGET_FRAC[sec])))
        for sec in SECTIONS
    }
    section_year_ranges = _compute_section_year_ranges(
        timeline, speech_window)
    value_mode = narration_cfg.get("value_mode", "total")
    metric_label = (narration_cfg.get("trend_label")
                    or narration_cfg.get("video_title")
                    or "the metric on screen")
    user_payload = {
        "tone": tone,
        "words_per_second": wps,
        "video_duration_seconds": duration,
        "speech_window_seconds": speech_window,
        "target_word_count_total": target_words,
        "section_word_budgets": section_budgets,
        "section_year_ranges": section_year_ranges,
        "value_mode": value_mode,
        "value_mode_note": _value_mode_note(value_mode),
        "metric_label": metric_label,
        "video_title": narration_cfg.get("video_title", ""),
        "year_to_seconds_map": timeline["year_to_seconds"],
        "events": timeline["events"],
        "stat_pack": stat_pack,
    }
    common_meta = {
        "video_duration_seconds": duration,
        "words_per_second": wps,
        "target_word_count_total": target_words,
        "section_word_budgets": section_budgets,
        "tone": tone,
    }
    return user_payload, common_meta


_WORLD_SYSTEM_PROMPT = _WORLD_BASE_PROMPT + _WORLD_VARIANTS_ADDENDUM


def _resolve_system_prompt(narration_cfg: dict | None) -> str:
    """Return the full system-prompt text for the requested channel.

    If `narration_cfg["system_prompt_module"]` is set, import that module and
    return its `SYSTEM_PROMPT` constant (channel-specific, self-contained —
    must already include its own variants-mode addendum). Default: the
    world-stats prompt (base + variants addendum)."""
    if narration_cfg:
        mod_path = narration_cfg.get("system_prompt_module")
        if mod_path:
            import importlib
            try:
                mod = importlib.import_module(mod_path)
            except ImportError as exc:
                raise RuntimeError(
                    f"narration.system_prompt_module={mod_path!r} could not be "
                    f"imported: {exc}"
                ) from exc
            try:
                return mod.SYSTEM_PROMPT
            except AttributeError as exc:
                raise RuntimeError(
                    f"narration.system_prompt_module={mod_path!r} has no "
                    f"SYSTEM_PROMPT attribute"
                ) from exc
    return _WORLD_SYSTEM_PROMPT


def _system_blocks(narration_cfg: dict | None = None) -> list[dict]:
    return [{
        "type": "text",
        "text": _resolve_system_prompt(narration_cfg),
        "cache_control": {"type": "ephemeral"},
    }]


def _usage_dict(response) -> dict:
    return {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_read_input_tokens": getattr(
            response.usage, "cache_read_input_tokens", 0),
        "cache_creation_input_tokens": getattr(
            response.usage, "cache_creation_input_tokens", 0),
    }


def _pad_or_trim(options: list[str], n: int) -> list[str]:
    """Claude sometimes misses the count by one; trim extras and warn on shortfall."""
    if not options:
        return []
    if len(options) > n:
        return options[:n]
    return options


def generate_variants(*, stat_pack: dict, timeline: dict,
                      narration_cfg: dict, out_path: Path) -> dict[str, Any]:
    """Call Claude once for all three sections, write cache/variants.json."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Export it or add it to `.env`."
        )
    client = anthropic.Anthropic(api_key=api_key)
    model = narration_cfg.get("model", "claude-opus-4-7")

    user_payload, common_meta = _build_variant_payload(
        stat_pack=stat_pack, timeline=timeline, narration_cfg=narration_cfg)

    emitted, response = _call_variants(
        client=client, model=model, system_blocks=_system_blocks(narration_cfg),
        user_payload=user_payload, sections=SECTIONS,
    )

    doc = {
        "hooks": _pad_or_trim([s.strip() for s in emitted.get("hooks", [])], SECTION_COUNTS["hook"]),
        "middles": _pad_or_trim([s.strip() for s in emitted.get("middles", [])], SECTION_COUNTS["middle"]),
        "endings": _pad_or_trim([s.strip() for s in emitted.get("endings", [])], SECTION_COUNTS["ending"]),
        "meta": {
            "generated_at": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            "model": model,
            **common_meta,
            "usage": _usage_dict(response),
        },
    }

    for sec, arr in (("hook", doc["hooks"]), ("middle", doc["middles"]),
                     ("ending", doc["endings"])):
        print(f"[variants] {sec}: {len(arr)}/{SECTION_COUNTS[sec]} options")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"→ wrote {out_path}")
    return doc


def regenerate_section(*, section: str, stat_pack: dict, timeline: dict,
                       narration_cfg: dict, out_path: Path) -> dict[str, Any]:
    """Re-roll just one section (hook / middle / ending); merge into existing variants.json."""
    if section not in SECTIONS:
        raise ValueError(f"section must be one of {SECTIONS}, got {section!r}")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Export it or add it to `.env`."
        )
    client = anthropic.Anthropic(api_key=api_key)
    model = narration_cfg.get("model", "claude-opus-4-7")

    user_payload, common_meta = _build_variant_payload(
        stat_pack=stat_pack, timeline=timeline, narration_cfg=narration_cfg)

    emitted, response = _call_variants(
        client=client, model=model, system_blocks=_system_blocks(narration_cfg),
        user_payload=user_payload, sections=(section,),
    )

    if out_path.exists():
        try:
            doc = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            doc = {"hooks": [], "middles": [], "endings": [], "meta": {}}
    else:
        doc = {"hooks": [], "middles": [], "endings": [], "meta": {}}

    plural = {"hook": "hooks", "middle": "middles", "ending": "endings"}[section]
    new_options = _pad_or_trim(
        [s.strip() for s in emitted.get(plural, [])],
        SECTION_COUNTS[section],
    )
    doc[plural] = new_options
    print(f"[variants] regenerated {plural}: {len(new_options)}/{SECTION_COUNTS[section]} options")

    doc.setdefault("meta", {})
    doc["meta"].update({
        "generated_at": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        "model": model,
        **common_meta,
        f"last_regenerated_section": section,
        "usage_last": _usage_dict(response),
    })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"→ wrote {out_path}")
    return doc
