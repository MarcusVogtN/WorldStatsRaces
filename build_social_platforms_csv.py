"""Build a dense Year x Platform monthly-active-users matrix (MAU in millions).

Figures are approximate, hand-assembled from public annual-report / press
milestones. This is a TEST dataset for the social-platforms race; numbers are
directional, not audited. Where a platform reported only DAU, MAU is estimated.
"""
import csv

# MAU in MILLIONS. Keys are years with published/anchor figures; gaps within a
# platform's active span are linearly interpolated. Years outside the span are
# omitted (no bar).
DATA = {
    "Friendster": {2003: 3, 2004: 7, 2005: 7, 2006: 5, 2007: 3},
    "MySpace":    {2004: 5, 2005: 25, 2006: 55, 2007: 75, 2008: 110, 2009: 100,
                   2010: 70, 2011: 35, 2012: 25, 2013: 18},
    "Orkut":      {2004: 8, 2005: 20, 2006: 35, 2007: 50, 2008: 80, 2009: 100,
                   2010: 100, 2011: 100, 2012: 90, 2013: 55},
    "Facebook":   {2004: 1, 2005: 6, 2006: 12, 2007: 50, 2008: 145, 2009: 360,
                   2010: 608, 2011: 845, 2012: 1056, 2013: 1230, 2014: 1390,
                   2015: 1590, 2016: 1860, 2017: 2130, 2018: 2320, 2019: 2500,
                   2020: 2740, 2021: 2910, 2022: 2960, 2023: 3030, 2024: 3070},
    "YouTube":    {2005: 5, 2006: 50, 2007: 150, 2008: 300, 2009: 400, 2010: 480,
                   2011: 600, 2012: 800, 2013: 1000, 2014: 1100, 2015: 1300,
                   2016: 1500, 2017: 1600, 2018: 1900, 2019: 2000, 2020: 2300,
                   2021: 2500, 2022: 2560, 2023: 2490, 2024: 2500},
    "Twitter":    {2006: 1, 2007: 6, 2008: 20, 2009: 50, 2010: 100, 2011: 150,
                   2012: 200, 2013: 230, 2014: 290, 2015: 305, 2016: 317,
                   2017: 330, 2018: 326, 2019: 330, 2020: 353, 2021: 390,
                   2022: 430, 2023: 450, 2024: 420},
    "WhatsApp":   {2009: 1, 2010: 10, 2011: 50, 2012: 100, 2013: 300, 2014: 500,
                   2015: 900, 2016: 1000, 2017: 1300, 2018: 1500, 2019: 1600,
                   2020: 2000, 2021: 2000, 2022: 2240, 2023: 2400, 2024: 2500},
    "WeChat":     {2011: 50, 2012: 150, 2013: 300, 2014: 500, 2015: 650,
                   2016: 850, 2017: 980, 2018: 1080, 2019: 1150, 2020: 1210,
                   2021: 1250, 2022: 1310, 2023: 1340, 2024: 1360},
    "Instagram":  {2010: 1, 2011: 15, 2012: 50, 2013: 130, 2014: 300, 2015: 400,
                   2016: 600, 2017: 800, 2018: 1000, 2019: 1000, 2020: 1220,
                   2021: 1480, 2022: 2000, 2023: 2000, 2024: 2000},
    "Snapchat":   {2012: 20, 2013: 50, 2014: 100, 2015: 150, 2016: 250,
                   2017: 290, 2018: 310, 2019: 360, 2020: 400, 2021: 500,
                   2022: 560, 2023: 660, 2024: 800},
    "TikTok":     {2017: 100, 2018: 270, 2019: 500, 2020: 700, 2021: 1000,
                   2022: 1400, 2023: 1500, 2024: 1600},
    "Pinterest":  {2012: 25, 2013: 50, 2014: 70, 2015: 100, 2016: 150,
                   2017: 200, 2018: 250, 2019: 300, 2020: 440, 2021: 450,
                   2022: 450, 2023: 480, 2024: 520},
    "Reddit":     {2010: 20, 2012: 50, 2014: 100, 2016: 250, 2018: 330,
                   2020: 430, 2022: 500, 2023: 550, 2024: 600},
}


def densify(points):
    years = sorted(points)
    lo, hi = years[0], years[-1]
    out = {}
    for y in range(lo, hi + 1):
        if y in points:
            out[y] = points[y]
        else:
            # linear interp between surrounding anchors
            prev = max(a for a in years if a < y)
            nxt = min(a for a in years if a > y)
            frac = (y - prev) / (nxt - prev)
            out[y] = round(points[prev] + frac * (points[nxt] - points[prev]), 1)
    return out


rows = []
for platform, pts in DATA.items():
    for year, val in densify(pts).items():
        rows.append((platform, year, val))

rows.sort(key=lambda r: (r[0], r[1]))
with open("social_platforms_mau.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Platform", "Year", "MAU"])
    w.writerows(rows)

print(f"wrote social_platforms_mau.csv: {len(rows)} rows, "
      f"{len(DATA)} platforms, years {min(r[1] for r in rows)}-{max(r[1] for r in rows)}")
