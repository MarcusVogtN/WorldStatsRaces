# Dataset ideas for race videos

Re-ranked around **virality**, not data category. The pipeline accepts any
source that yields a Year×entity matrix; it is no longer World-Bank-only:

- `world_bank` — country indicators (flags). `config.json::source.indicator`.
- `csv` — any tidy country CSV (flags), e.g. OWID/WHO exports.
- `ssa_names` — US baby names (letter avatars). `source.sex` = `F`|`M`.
- New entity types plug in via a `DataSource` + an `AssetProvider`
  (`letter` avatars need no art; `flags` for countries).

**What actually goes viral** (learned the hard way — macro country races are a
saturated genre):
1. **Relatability** — the viewer is *in* the data (their name, their city,
   their decade, their vice). Beats "Luxembourg GDP per capita" every time.
2. **Churn** — the lead must change hands. Flat #1 = dead video.
3. **A known story beat** the audience half-remembers (USSR collapse, 2008,
   COVID, the rise of TikTok).
4. **A counterintuitive reveal** — the "wait, what?" that earns the comment.

---

## Tier S — purple cows (new entity types / fresh sources)

These don't look like every other chart-race channel. Highest priority.

| Idea | Source | Asset | Hook |
|---|---|---|---|
| **Baby girl names (US)** | `ssa_names` F | letter | **SHIPPED.** Mary 7.8%→ top name 1.1%: dominance collapses into a free-for-all. |
| **Baby boy names (US)** | `ssa_names` M | letter | **RENDERED** (awaiting upload). John's ~40yr reign → Michael → Liam/Noah; 8%→1.3% collapse. Less churn than girls but the long reigns land. |
| **Most populous cities (world)** | Chandler/UN historical urban pop CSV | letter/text | Babylon→Rome→Beijing→London→NYC→Tokyo→Delhi. "Your city" hook, centuries of churn, almost nobody races *cities*. |
| **Biggest companies by market cap** | companiesmarketcap / stooq CSV | letter (logos later) | Tribal (Apple/MSFT/Aramco/Nvidia). The Nvidia 2023–24 vertical takeoff is a built-in jaw-drop. |
| **Social platforms by monthly users** | hand-built CSV (annual reports) | letter | MySpace→Facebook→Instagram→TikTok. Small CSV, huge nostalgia, clean villain-rotation. |
| **Olympic gold medals (cumulative)** | Kaggle 120-yrs Olympic history CSV | flags | Recurring event hook every 2 yrs; USA/USSR/China arc; `accumulated` mode. |
| **Highest-grossing movies / franchises** | Box Office Mojo CSV | letter (posters later) | Titanic→Avatar→Avengers. Pop-culture relatability; argument bait. |
| **Most popular dog breeds (US)** | AKC annual registrations CSV | letter | Cocker→Lab→Frenchie. Wholesome, shareable, "what happened to the Rottweiler?" |

## Tier A — country races worth keeping (flags, WB/CSV)

Strongest of the macro set: real churn + a story everyone half-knows.

| Idea | Indicator / source | Mode | Hook |
|---|---|---|---|
| **GDP** | `NY.GDP.MKTP.CD` | total | China overtakes Japan (2010), closes on US. The spine. |
| **CO₂ — total *and* accumulated** | `EN.ATM.CO2E.KT` | total + `accumulated` | Two-video combo: current emitter (China) vs who *caused* it (US). The contrast is the point. |
| **Foreign-exchange reserves** | `FI.RES.TOTL.CD` | total | China's post-2000 explosion is unmissable; one clear protagonist. |
| **Population** | `SP.POP.TOTL` | total | China↔India crossover (~2023) as the climax. |
| **Life expectancy** | `SP.DYN.LE00.IN` | total | Soviet collapse = a visible *drop*; COVID dip 2020–21. |
| **Patent applications (residents)** | `IP.PAT.RESD` | total | Japan→China handoff — a cleaner arc than GDP. |
| **International tourism arrivals** | `ST.INT.ARVL` | total | Built-in COVID-2020 cliff; France/Spain/US fight. |
| **Inflation, consumer prices** | `FP.CPI.TOTL.ZG` | rate | Hyperinflation parade (Zimbabwe/Venezuela/Argentina). Chaotic = attention. |
| **Military spending** | `MS.MIL.XPND.CD` (total) / `…GD.ZS` (% GDP) | total/rate | Sibling to the shipped per-capita version; % GDP reframes "who cares most." |
| **Remittances received** | `BX.TRF.PWKR.CD.DT` | total / per_capita | India/Mexico/Philippines; per-capita flips to tiny islands (Tonga). |
| **External debt stocks** | `DT.DOD.DECT.CD` | total | Argentina/Turkey/Brazil drama. |

## Tier B — relatable "vice & body" country races (OWID/WHO via `csv`)

More clickable than macro money, but country-level so still flags. Need an
OWID/WHO CSV download (no WB indicator). Verify timeframe/churn before render.

| Idea | Source | Hook |
|---|---|---|
| **Obesity rate** | OWID/WHO | Pacific islands + Gulf + US; "is the US really #1?" reveal. |
| **Alcohol consumption per capita** | WHO/OWID | Eastern Europe dominance; Russia/Moldova/Czechia. |
| **Meat consumption per capita** | OWID | US/Argentina/Australia; China's climb. |
| **Cigarettes / smoking** | OWID/WHO | Rise then fall — the decline arc is the story. |
| **Internet users (% pop)** | `IT.NET.USER.ZS` | 1995→2020 climb; Nordics early, Gulf leapfrog. |
| **World Happiness score** | World Happiness Report CSV | Nordic lock at top; short timeframe (2005+) is the weakness. |

---

## Removed / parked (and why)

Pruned from the old list — low churn, redundant, or rendering headaches.
Don't resurrect without a reason.

- **Urban population, high-tech exports, energy use per capita, air transport
  passengers** — redundant with population / patents / CO₂-per-capita /
  tourism respectively.
- **Out-of-pocket health spending, government education spending** — confusing
  "worst-wins" inverse framing; weak hook.
- **Net migration** — signed values need renderer work. Park until needed.
- **FDI net inflows, mobile subscriptions, container port traffic** — too
  volatile / >100% artifacts / timeframe too short. Park.
- **R&D %, arms exports, armed-forces personnel, refugees, physicians,
  forest area, goods exports, GDP per capita** — fine but mid; pull from here
  only if a Tier S/A idea stalls. (Physicians + military-per-capita already
  shipped.)

# Saved drafts (rendered, awaiting review)

- **Refugees by country of asylum** — `output/refugees_race_narrated.mp4`
  (2026-05-12). User paused upload, wanted a lighter topic. Still valid.

---

## How to execute any of these

**Country / WB idea:** edit `config.json` — `source.type:"world_bank"`,
`source.indicator`, `source.timeframe`, `video_title`, `output_filename`,
`per_capita`/`accumulated`, `trend_label`, `value_format`.

**Country CSV (OWID/WHO):** `source.type:"csv"`, `path`, `value_col`,
`country_col`, `year_col`, `filters`, `timeframe`. Flags resolve via pycountry.

**Baby names:** `source.type:"ssa_names"`, `source.sex:"F"|"M"`,
`assets.type:"letter"`, `value_scale:100`, `value_format:"decimal1"`,
`value_suffix:"%"`. (This is the shipped girls' config — flip `sex` for boys.)

Then:

```bash
python run.py --refetch            # pull source + assets
python run.py --preview-frames auto # eyeball layout across the timeframe
python run.py --generate-variants && python run.py --auto-assemble
python run.py --generate-narration  # TTS + render + mux (narrated mp4)
```

**Music budget:** the narrated video must be **≤ 47.0s** (the music track
length) — never longer, or the music loops. The timing-fit quantizes
`steps_per_year` to an integer, so body length snaps to discrete values; if the
total overruns, lower `render.narration.max_speech_coverage` to shorten the
voice until the body lands under budget. Do **not** speed up audio.

## Previewing before a full render

```bash
python run.py --preview-frame 1995
python run.py --preview-frames auto   # 5 frames across the timeframe
```

If two frames look identical, the race is too flat — pick another dataset.
