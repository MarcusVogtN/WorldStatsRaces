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


SYSTEM_PROMPT = """You're writing voiceover for a 45-second vertical YouTube \
Shorts bar-chart race. One take, straight through, hype and casual — like \
you're on the couch reacting with a friend, not anchoring the 6 o'clock \
news.

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
- BAD (slang sprinkled, not committed): "America has been spending a lot \
of money on its military since the 1960s."
- GOOD (hype friend, online): "ok so America's been running this thing \
since the SIXTIES — like, deadass the entire time, no cap."
- GOOD (the turn): "but wait — China just popped off out of nowhere?? \
respectfully, the way they're climbing this chart is unhinged."

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
- Example flow (use real numbers from `final_standings` / events; these \
are placeholders):
  hype:        "no way, China's been QUIETLY climbing this whole time—"
  broadcaster: "China's military spending has expanded at a sustained, accelerating rate over the period."
  hype:        "—and they are NOT slowing down, absolutely menacing pace."

# GROUND TRUTH — never invent facts (HARD RULES)
- Country whitelist: you MAY ONLY name countries that appear in \
`stat_pack.countries_in_data`. If a country is not in that list, it is \
NOT in the video and you MUST NOT mention it. In particular: NEVER \
mention "USSR", "Soviet Union", "Yugoslavia", "East Germany", or any \
other historical entity unless its exact display name is in that list. \
This dataset uses present-day country names only — when a country like \
Russia first appears mid-video, narrate it as "Russia shows up" / \
"Russia enters the race", NOT as "the Soviet Union collapses".
- NO NUMERIC VALUES. Never quote a dollar figure, a per-person figure, a \
percentage of GDP, or any other monetary amount — not in the hook, not in \
the middle, not in the ending. The on-screen ticker shows the numbers; \
your job is reactions and storytelling, not stats. Banned: "$916 B", \
"916 billion", "nearly a trillion", "$2,500 per person", "30% of GDP", \
"twice as much", "doubled to X", any digits attached to a money word. \
Allowed: vague qualitative comparisons ("blowing everyone else out of \
the water", "miles ahead", "lapping the field", "barely a dot on the \
chart"). If you feel the urge to type a number with a currency or "per \
capita" next to it — don't.
- Years and counts (e.g. "64 straight years at #1"): use \
`stat_pack.longest_reign_at_1.years`. Do not guess. Calendar years and \
ordinal ranks (#1, #2) are fine; monetary values are not.
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
shaking"), country-character storytelling, jokes, vibes, observations \
about the race overall, foreshadowing without naming the swap. Tease the \
shape of what's coming, don't call the exact moment.
- Rank-1 / final-ranking claims are allowed ONLY in the ending section, \
where the chart has stabilized and timing isn't a problem.

# Tense & foreshadowing — FUTURE, NEVER SPOIL
- Write as if the events are ABOUT TO HAPPEN on screen. Build anticipation.
- Use future/expectation phrases: "watch what happens", "wait for it", \
"any second now", "keep your eye on", "here comes", "just wait", "you're \
about to see", "coming up".
- NEVER spoil the final ranking in the first half. Numbers are off-limits \
everywhere (see HARD RULES above), so the payoff is the *reveal* — who \
wins, who got lapped, the "64 straight years" stat — never a dollar \
figure.
- The first sentence is a HOOK and a QUESTION. Pull the viewer in, get \
them curious, get them guessing.

# Opening — QUESTION, not a summary
- Start with ONE engaging question in ≤10 words. Examples:
  - "Which country do you think spends the most on their military?"
  - "Guess how much the US spends compared to everyone else."
  - "Watch what happens when you line up 60 years of military budgets."
- Do NOT reveal the answer in the opening. Tease it, then make the viewer \
watch.

# Structure — ONE LINEAR STORY, 3 BEATS
- Three (max four) beats. ONE coherent story. NOT a list of facts. NOT a \
year-by-year rundown.
- Beat 1 (hook): the opening question + setup. "Watch this race start…"
- Beat 2 (the turn): the single biggest moment mid-video. Foreshadow it \
before it hits — "ok but something crazy is about to happen around the \
90s" — then let it land when it's on screen. Add a plain-language \
real-world "why" in one sentence ONLY if it relates to a country that \
is actually in `stat_pack.countries_in_data` (e.g. "China just opens \
the spending floodgates", "oil money kicks in"). Do NOT invoke a \
historical entity that is not in the dataset (no USSR, no Yugoslavia).
- Beat 3 (the payoff): the ending reveal. Land the final RANKING and any \
"wow" stat from `stat_pack` (years-at-#1, etc.). NO dollar amounts — the \
ticker on screen handles those.
- Each beat flows into the next. Connected sentences, not bullet points.

# Real-world 'why'
You MAY add ONE short plain-language real-world reason for the big \
turn — but ONLY if (a) the subject is a country in \
`stat_pack.countries_in_data`, and (b) the reason is general/economic \
("oil money kicked in", "post-9/11 buildup", "economic boom"). If \
you're tempted to attribute the turn to a country/entity not in the \
dataset, drop the 'why' entirely and just describe what's on screen. \
NEVER dwell on casualties, conflicts, or specific politicians.

# Length — HIT THE WORD BUDGET
- Target word count comes in the user payload. Hit it ±10%.
- The word count is tuned so the LAST WORD lands right before the end of \
the video. Short means dead air; long means cut off mid-sentence.
- Count your words before emitting.

# Output
Call the `emit_script` tool exactly once with `script_text` and \
`suggested_trim`. Do not output prose outside the tool call.
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


SCRIPT_TOOL = {
    "name": "emit_script",
    "description": "Emit the continuous commentator script and an optional trim suggestion.",
    "input_schema": {
        "type": "object",
        "properties": {
            "suggested_trim": {
                "type": ["object", "null"],
                "description": "Null if the full timeframe is fine, otherwise a trim suggestion.",
                "properties": {
                    "start_year": {"type": "integer"},
                    "reason": {"type": "string"},
                    "boringness": {"type": "number"},
                },
                "required": ["start_year", "reason"],
            },
            "script_text": {
                "type": "string",
                "description": "Single continuous commentator script, read straight through over the whole video. One paragraph. Starts with a question. Builds in the future tense. Pays off at the end.",
            },
        },
        "required": ["script_text"],
    },
}


def generate_script(*,
                    stat_pack: dict,
                    timeline: dict,
                    narration_cfg: dict,
                    out_path: Path) -> dict[str, Any]:
    """Call Claude, validate length, write cache/narration.json."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Export it or add it to `.env`."
        )

    client = anthropic.Anthropic(api_key=api_key)
    model = narration_cfg.get("model", "claude-opus-4-7")
    wps = float(narration_cfg.get("words_per_second", 2.7))
    coverage = float(narration_cfg.get("max_speech_coverage", 0.6))
    tone = narration_cfg.get("tone", "hype friend, casual, loud")
    duration = float(timeline["video_duration_seconds"])
    # Pace speech to end before any hold on the final frame.
    speech_window = float(timeline.get("animation_seconds", duration))
    target_words = int(speech_window * wps * coverage)

    value_mode = narration_cfg.get("value_mode", "total")
    user_payload = {
        "tone": tone,
        "words_per_second": wps,
        "video_duration_seconds": duration,
        "speech_window_seconds": speech_window,
        "target_word_count": target_words,
        "value_mode": value_mode,
        "value_mode_note": _value_mode_note(value_mode),
        "year_to_seconds_map": timeline["year_to_seconds"],
        "events": timeline["events"],
        "stat_pack": stat_pack,
    }

    system = [{
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }]

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        tools=[SCRIPT_TOOL],
        tool_choice={"type": "tool", "name": "emit_script"},
        messages=[{
            "role": "user",
            "content": [{
                "type": "text",
                "text": (
                    f"Write ~{target_words} words (±10%) for a "
                    f"{duration:.1f}-second video. Open with a QUESTION. "
                    "Write in the future tense — tease what's coming, do NOT "
                    "reveal the final numbers until the last beat. Three "
                    "beats, one linear story. Hype friend voice, not news "
                    "anchor. Count your words before emitting.\n\n"
                    + json.dumps(user_payload, ensure_ascii=False)
                ),
            }],
        }],
    )

    script_doc: dict[str, Any] | None = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "emit_script":
            script_doc = block.input  # type: ignore[assignment]
            break
    if script_doc is None:
        raise RuntimeError("Model did not call `emit_script`. Response: "
                           + repr(response.content))

    script_text: str = script_doc["script_text"].strip()
    word_count = len(script_text.split())
    est_seconds = word_count / wps
    print(f"[narration] script: {word_count} words, ~{est_seconds:.1f}s of speech "
          f"(target {target_words} words / {duration:.1f}s video)")
    if est_seconds > duration * 1.1:
        print(f"[narration] warn: script may overrun video by "
              f"{est_seconds - duration:.1f}s")

    script_doc["script_text"] = script_text
    script_doc.setdefault("meta", {})
    script_doc["meta"].update({
        "generated_at": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        "model": model,
        "video_duration_seconds": duration,
        "words_per_second": wps,
        "target_word_count": target_words,
        "actual_word_count": word_count,
        "estimated_seconds": round(est_seconds, 2),
        "tone": tone,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_read_input_tokens": getattr(
                response.usage, "cache_read_input_tokens", 0),
            "cache_creation_input_tokens": getattr(
                response.usage, "cache_creation_input_tokens", 0),
        },
    })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(script_doc, f, ensure_ascii=False, indent=2)
    print(f"→ wrote {out_path}")
    return script_doc


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
        "Beat 1 — pure curiosity bait. ≤10 words each. Open a loop in the "
        "viewer's head; do NOT close it. NEVER reveal a country name, a "
        "rank, a number, or any outcome. Speak generally about the race. "
        "Hype voice only — never the broadcaster cut-in. Each of the 5 "
        "options must be genuinely different (different angle, different "
        "phrasing). Examples of vibe (do not copy): 'guess who runs this "
        "thing', 'one of these countries snaps', 'watch the leaderboard go "
        "feral'."
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
        "'someone's about to make a run'), tell a quick story about a "
        "country's run on the chart, drop a joke or observation about the "
        "race vibe, foreshadow without naming the swap. This is also the "
        "place for the ONE broadcaster cut-in sentence — but it too stays "
        "inside the middle window AND obeys the no-play-by-play rule (it "
        "can describe a country's general run, not 'reaches second place "
        "in 2008'). Each of the 3 options should take a meaningfully "
        "different angle (different country focus, different joke, "
        "different vibe)."
    ),
    "ending": (
        "Beat 3 — the payoff. You may ONLY refer to the year window given "
        "in `section_year_ranges.ending` (final stretch of the race). NO "
        "dollar values, NO per-person figures, NO percentages — the ticker "
        "on screen shows the numbers. Land the final RANKING and any wow "
        "stat from stat_pack (longest-reign-at-#1 in years, total years on "
        "screen, etc.). Hype voice only — never the broadcaster cut-in. "
        "Each of the 3 options should land the payoff differently (pure "
        "rank-1 flex, top-3 sweep, longest-reign stat, biggest climber)."
    ),
}

VARIANTS_ADDENDUM = """

# VARIANTS MODE
You are writing short SECTION options, NOT a full script. The full script has
three beats (hook → turn → payoff); each run of this tool emits alternatives
for ONE OR MORE beats so a human editor can pick the best combo.

- Each option is a standalone snippet for its beat — a couple of sentences,
  self-contained, readable on its own.
- Respect the per-section word budget in the user payload. Aim for the target
  ±15%.
- Respect the hook/payoff rule: the broadcaster cut-in sentence appears ONLY
  in `middle`, NEVER in `hook` or `ending`.
- Options within a section must be meaningfully different — different angle,
  different focus, different rhythm. No reworded near-duplicates.
- All other rules from the main system prompt still apply (country whitelist,
  NO numeric/dollar values anywhere, future tense for hook/middle, no USSR
  unless in `countries_in_data`, 10-year-old reading level).
- HARD NO-SPOILER RULE. The viewer should not know how the race ends until the
  ending plays. Therefore:
    - The HOOK names NO countries, NO ranks, NO numbers. It is pure curiosity
      bait — open a loop, do not close it.
    - The MIDDLE may only describe what happens inside its year window
      (`section_year_ranges.middle`). It MUST NOT name the eventual winner,
      MUST NOT quote any final-year value, MUST NOT say "ends up at #X" or
      "finishes at $Y". If a country is climbing in the middle window, narrate
      only the climb you can see — never its destination.
    - The ENDING is the only place final numbers and the final ranking are
      allowed. Stay inside `section_year_ranges.ending`.
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
- Variety across hook options: rotate the slang and the opening syntax.
  One can be a "tell me why", one can be a flat ironic question, one can
  be ALL CAPS, one can be a "wait …" cold-open, etc. Don't emit five
  "guess how much" variants and don't reuse the same opener twice.

# Output
Call the `emit_variants` tool exactly once with one array field per requested
section (`hooks`, `middles`, `endings`). Omit arrays for sections you were not
asked to produce. Do not output prose outside the tool call.
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
                "description": "Opening-question snippets (beat 1). 5 options.",
                "items": {"type": "string"},
            },
            "middles": {
                "type": "array",
                "description": "Turn snippets (beat 2). 3 options. Each must contain the one broadcaster cut-in sentence.",
                "items": {"type": "string"},
            },
            "endings": {
                "type": "array",
                "description": "Payoff snippets (beat 3). 3 options. Land the final RANKING from stat_pack — NO dollar values or numeric figures (the ticker on screen handles numbers).",
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


def _system_blocks() -> list[dict]:
    return [{
        "type": "text",
        "text": SYSTEM_PROMPT + VARIANTS_ADDENDUM,
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
        client=client, model=model, system_blocks=_system_blocks(),
        user_payload=user_payload, sections=SECTIONS,
    )

    doc = {
        "hooks": _pad_or_trim([s.strip() for s in emitted.get("hooks", [])], 5),
        "middles": _pad_or_trim([s.strip() for s in emitted.get("middles", [])], 3),
        "endings": _pad_or_trim([s.strip() for s in emitted.get("endings", [])], 3),
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
        client=client, model=model, system_blocks=_system_blocks(),
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
