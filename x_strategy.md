# X Strategy — @WorldStatsRaces

Notes from digging through X's open-sourced algorithm (github.com/xai-org/x-algorithm, cloned + analyzed 2026-07-08).

## Diagnosis: why posts get ~12 views

Not shadowbanned — invisible by default. Root causes found in the code:

1. **Cold-start retrieval problem** (`phoenix/` two-tower retrieval): posts only enter "For You" if their embedding matches a user's interest history. Embeddings strengthen from engagement received. Zero engagement → generic weak embedding → never retrieved → zero out-of-network reach. Chicken-and-egg.
2. **Low-follower spam screening** (`grox/classifiers/content/spam.py` — `SpamEasiLowFollowerClassifier`): low-follower accounts get an extra AI spam check that bigger accounts skip. Repetitive, scheduled, broadcast-only posting patterns are exactly what it screens for.
3. **Quality gate at 0.4** (`grox/classifiers/content/banger_initial_screen.py`): AI scores each post; below 0.4 = marked negative. Bland/duplicate captions drag the score down.
4. **Negative-signal predictions weighted heavily** (`home-mixer/scorers/weighted_scorer.rs`): predicted report/block/not-interested carry large negative weights. Unknown accounts with bot-like patterns get pessimistic predictions.
5. **Video boost only above a min duration** — our videos clear this. Native video + Premium + no hashtags: all already correct.
6. **File metadata is irrelevant** — platforms strip and re-encode everything; verified our MP4s are clean and within spec anyway.

## Strategy (breaks the cold-start loop)

- **Reply daily** — the only free distribution for a tiny account. Replies appear under big accounts' posts → first eyeballs → first likes → retrieval model finally gets a signal. Target mid-size stats/football/data-viz accounts (not mega accounts, reply drowns there).
- **Vary captions, ask questions** — predicted-reply probability is a big positive ranking weight. E.g. "Did you know X led until 1994?" Avoid identical caption format every post (duplicate/low-diversity suppression).
- **Quote-post / attach videos to trending conversations** occasionally — rides existing engagement streams.
- **Evaluate after 3-4 weeks** of genuine engagement. If still ~12 views, then suspect an actual flag and appeal/check account status.

## Idea: reply-target finder (TODO)

Build a way to **find tweets worth replying to with a stat race** (or another video/post format matching what this page posts). Concept:

- Search/monitor X for tweets in our niches (country comparisons, sports stats, economy, population, music charts) that are getting traction.
- Match tweet topic → existing rendered race in `output/` (or a quick re-render with relevant highlight).
- Reply with the relevant video/stat + a short punchy line.
- This turns the reply-daily grind into a semi-systematic pipeline and puts our content exactly where an interested audience already is.

Open questions: X API costs for search (free tier is very limited), vs. manual daily browse with a checklist, vs. scraping. Start manual, automate if it works.
