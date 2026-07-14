# Correlation-video ideas

A **different format** from the racing-bars pipeline. Do NOT feed these to
`make-world-stats-video` / `make-sports-stats-video` — those render Year×entity
bar races. A correlation video is **two trend lines climbing together (or not)
with a live "correlation: XX%" counter, then a reveal.**

**Status: unbuilt format.** Needs either a small new dual-line renderer, or a
cheap faked pilot first to test if "correlation reveal" lands on the channel.
Recommendation: build ONE throwaway pilot before investing in a renderer.

Three sub-genres, in rough order of strength:
1. **Question format** (strongest) — title is a question people already argue
   about; test it live; ✅ yes / ❌ no / 🤷 unknown are all satisfying. You
   literally can't lose.
2. **Real / surprising** — genuine hidden third-factor; the reveal is the payoff.
3. **Spurious / absurd** — funny coincidence, zero real link (Tyler Vigen goldmine).

Payoff key: ✅ likely yes · ❌ likely no (best twist) · 🤷 genuinely unknown

---

## Genre 1 — Question format (test it in the video)

### World-stats channel
| Question (= title) | Test | Payoff | Data |
|---|---|---|---|
| Does more money make a country happier? | GDP/capita vs happiness | ✅ flattens — show the ceiling | World Happiness Report + World Bank |
| Do rich countries have fewer babies? | GDP/capita vs birth rate | ✅ strong & surprising | World Bank |
| Does more homework = smarter kids? | homework hrs vs PISA | ❌ ~none — great twist | OECD PISA |
| Do sunnier countries live longer? | sunshine hrs vs life expectancy | ❌ nope (money wins) | Our World in Data |
| More guns = more gun deaths? | guns/capita vs gun deaths | ✅ spicy = comments | Small Arms Survey |
| Do cold countries drink more? | latitude vs alcohol/capita | ✅ yes, genuinely odd | WHO |
| Does more McDonald's = fatter country? | outlets/capita vs obesity | 🤷 test live | WHO + store counts |
| Do beautiful people earn more? | attractiveness vs income | ✅ halo effect is real | research-backed |

### Sports-stats channel
| Question (= title) | Test | Payoff | Data |
|---|---|---|---|
| Does your birth MONTH decide if you go pro? | pro players' birth-month spread | ✅ **huge** — relative-age effect | player DBs / FotMob |
| Does spending the most win the league? | wage bill vs table position | ✅ mostly — show exceptions | Transfermarkt |
| Are taller strikers better scorers? | height vs goals | ❌ weak — clean "nope" | FotMob |
| Do home teams really win more? | home vs away win % | ✅ but shrinking | league data |
| Does loving soccer = being good at it? | interest/players vs FIFA rank | 🤷 test it | FIFA |
| Do older players get more red cards? | age vs cards | 🤷 unknown | match data |

---

## Genre 2 — Real / surprising (hidden third factor)
| The two lines | Hidden cause / twist | Note |
|---|---|---|
| Ice cream sales vs shark attacks | summer heat | the classic — teaches the concept |
| Chocolate/capita vs Nobel Prizes (by country) | both track wealth; r≈0.79 published | sounds fake, is real & citable |
| Height vs income | ~+3% pay taller; ~$166k/career 6ft vs 5'5" | mildly controversial = comments |
| Storks vs birth rates (by region) | rural land area / country size | "storks deliver babies… statistically?" |
| Firefighters sent vs fire damage | size of the fire | "obvious once you see it" |
| Kids' shoe size vs reading ability | age | wholesome, clean |
| Churches in a town vs crime | population size | spicy, drives debate |

## Genre 3 — Spurious / absurd (Tyler Vigen — CSVs downloadable free)
| The two lines | Hook | r |
|---|---|---|
| Nicolas Cage films vs pool drownings | "Did Nic Cage cause these drownings?" | ~66% (iconic) |
| Cheese eaten vs bedsheet-tangle deaths | "Cheese is killing people in their sleep" | ~95% |
| Maine divorce rate vs margarine consumption | "Stop eating margarine, save your marriage" | ~99% |
| Turkey eaten vs age of Miss America (inverse) | "More turkey → younger Miss America" | inverse |
| Liquor-store sales vs number of US bridges | "Every bridge = more drinking?" | 99.3% |
| Tea consumption vs lawnmower deaths | "Tea time is deadly" | high |
| US shrimp supply vs deaths by sharp glass | "More shrimp, more glass deaths" | high |
| iPhone sales vs people falling down stairs | "Your phone is throwing you down the stairs" | plausible-sounding |

---

## Genre 1 — Batch 2 (more questions)

### Personal / "about YOU" (strongest for Shorts — viewer is in the data)
| Question (= title) | Payoff | Note / data |
|---|---|---|
| Do people with more friends live longer? | ✅ strong | loneliness mortality studies |
| Does marriage make men live longer? | ✅ men yes, women less — twist | health surveys |
| Do dog owners live longer than cat owners? | ✅ dogs (more walking) | cohort studies |
| Do early risers earn more than night owls? | ✅ some evidence | verify effect size |
| Does swearing more mean you're more honest? | ✅ real study — great "wait what" | verify |
| Do night owls die younger? | ✅ real study | verify |
| Does being firstborn make you smarter? | ✅ small real IQ effect | birth-order research |
| Do people who read more earn more? | 🤷 test it | survey data |
| Does exercise actually make you smarter? | ✅ yes | cognition studies |

### World-stats — Batch 2
| Question (= title) | Payoff | Note / data |
|---|---|---|
| Do religious countries have more babies? | ✅ yes | religiosity vs fertility |
| Are countries near the equator more corrupt? | ✅ surprising real pattern | latitude vs corruption index |
| Does more vacation time make a country poorer? | ❌ no (Europe stays productive) | vacation days vs GDP/hour |
| Does daylight saving actually save energy? | ❌ debunked — great | energy studies |
| Do two countries with McDonald's ever go to war? | ❌-ish (Golden Arches theory) | famous, fun |
| Does more education = less crime? | ✅ yes | education vs crime rate |
| Do countries that recycle more pollute less? | 🤷 test it | OWID |
| Does more coffee = stronger economy? | 🤷 | coffee/capita vs GDP |

### Sports-stats — Batch 2
| Question (= title) | Payoff | Note / data |
|---|---|---|
| Do teams in RED kits win more? | ✅ real research says yes | kit colour vs win % |
| Does the team that scores first usually win? | ✅ show the % | match data |
| Do refs favour home teams? | ✅ real (added time, penalties) | match data |
| Does sacking the manager actually help? | ❌ "new-manager bounce" is a myth | before/after results |
| Does more possession = winning? | ❌ weak (anti-tiki-taka) | possession vs result |
| Do World Cup hosts overperform? | ✅ yes | tournament history |
| Do fixture-congested teams get more injuries? | ✅ likely | games vs injury rate |

Items marked "verify" rest on a single pop-sci study — sanity-check the data
exists and the effect is real before committing to a video.

---

## Genre 4 — Famous studies ("you were told X — is it true?")

The meta-hook: everyone half-remembers these. The **replication crisis** means
many were debunked or revised — that reversal is the payoff. Could run as a
series ("We fact-checked the famous studies").
Verdict: ✅ held up · ⚠️ weaker/revised than you were told · ❌ debunked

| Famous study (= title bait) | The claim | Verdict | The reveal |
|---|---|---|---|
| The Marshmallow Test | wait for the marshmallow → succeed in life | ⚠️ | 2018 replication: effect mostly vanishes once you control for family wealth |
| Power Posing (60M-view TED talk) | stand like Superman → more confident/successful | ❌ | failed to replicate; even the co-author walked it back |
| Harvard 80-Year Study | what makes a happy life? | ✅ | not money/fame — relationships; good marriage = men live ~12 yrs longer |
| "Money can't buy happiness" ($75k) | happiness plateaus at $75k/yr | ⚠️ | Killingsworth 2021 killed the plateau — it keeps rising with income |
| The 10,000-Hour Rule | 10k hrs of practice → mastery | ⚠️ | practice explains only ~12-26% of skill; talent/start-age matter more |
| Grit (Duckworth) | grit predicts success | ⚠️ | real but modest; barely beats plain conscientiousness |
| Blue Zones (live to 100) | lifestyle → extreme longevity | ⚠️ | many "zones" trace to bad birth records / pension fraud — spicy |
| Dunning-Kruger | the dumb think they're smart | ⚠️ | partly a statistical artifact; the effect is smaller than the meme |
| "Loneliness = 15 cigarettes/day" | isolation → early death | ✅ | Holt-Lunstad meta-analysis holds — social ties rival smoking/obesity |
| The French Paradox (red wine) | red wine → long life | ❌ | debunked; no safe amount, key researcher's data was retracted |
| The Mozart Effect | classical music → smarter baby | ❌ | debunked; tiny brief effect on adults, nothing on babies |
| Flynn Effect | each generation is smarter | ✅ | real for a century — but now **reversing** in rich countries (double twist) |
| The Beauty Premium (Hamermesh) | attractive people earn more | ✅ | real ~10-15% pay gap, both sexes |
| Height & leadership | taller → CEO / earns more | ✅ | real; huge over-representation of tall men in leadership |
| Smartphones & teen depression (Twenge/Haidt) | phones → teen mental-health crash | ⚠️ | correlation clear, causation fiercely debated = comment war |
| The "Hot Hand" in basketball | streak shooting is real | ⚠️ | called a myth for 30 yrs (1985), then partly **rehabilitated** in 2018 |

---

## Data sources
- Spurious CSVs: https://tylervigen.com/spurious-correlations
- World data: World Bank, Our World in Data, WHO, OECD PISA, World Happiness Report
- Sports: FotMob, Transfermarkt, fbref
