"""Static site builder for lottohelper.ca ("Draw Night" redesign, October 2026).

Renders every public page from:
  * content/*.html        hand-written pages and guides (body fragments + a JSON meta header)
  * draw_history.json     every Lotto 6/49 draw since 1982 and every Lotto Max draw since 2009
                          (backfilled Oct 2026, then appended nightly by main.py)

Outputs (repo root, served as-is by Vercel):
  index.html, lotto-max-results.html, lotto-649-results.html, check-my-numbers.html,
  lotto-odds-calculator.html, guides.html, 404.html, one .html per content/ file,
  data/lotto-max.json + data/lotto-649.json (compact history for the client-side tools),
  sitemap.xml, lastmod.json (real <lastmod> bookkeeping), jackpot_history.json (advertised
  jackpot snapshots per draw).

All numbers are rendered into the HTML at build time; JavaScript only adds the countdown,
count-up, tab switching and the interactive tools. Nothing here touches the network, so
`python main.py --build-only` is safe to run anywhere.

Tailwind scans this file: keep class names literal (see RANGE_CLASS / HEAT_CLASS).
Python 3.10 compatible (GitHub Actions runner): no nested same-quote f-strings.
"""
import hashlib
import html
import json
import math
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from itertools import combinations
from zoneinfo import ZoneInfo

SITE = "https://lottohelper.ca"
SITE_NAME = "lottohelper.ca"
ADSENSE_CLIENT = "ca-pub-5048509015899303"
ADSENSE_TAG = (
    '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
    '?client=ca-pub-5048509015899303" crossorigin="anonymous"></script>'
)
CSS_HREF = "/assets/site.css"
FONT_HREF = "/assets/fonts/baloo2-latin.woff2"
CONTENT_DIR = "content"
LASTMOD_FILE = "lastmod.json"
JACKPOT_FILE = "jackpot_history.json"
DATA_DIR = "data"

GOLD_BALL_START = 10_000_000
GOLD_BALL_STEP = 2_000_000
GOLD_BALL_BALLS = 30
MAX_JACKPOT_START = 10_000_000
MAXMILLIONS_FROM = 50_000_000
MAX_JACKPOT_CAP = 90_000_000

PT = ZoneInfo("America/Vancouver")
ET = ZoneInfo("America/Toronto")
# Both games: ticket sales close at 10:30 p.m. ET (7:30 p.m. PT) on draw night and the draw follows.
# Sources (checked Oct 7, 2026): OLG "LOTTO MAX draws take place every Tuesday and Friday after 10:30 PM ET";
# Loto-Quebec Lotto 6/49 "Deadline for wagers: Wednesdays and Saturdays at 10:30 p.m.";
# WCLC Lotto 6/49 + Lotto Max pages: tickets on sale "until ... 7:30 pm PT on the date of the draw".
DRAW_TIME_ET = (22, 30)

# ---------------------------------------------------------------------------
# AdSense manual units. Max 3 per page, reserved grey boxes away from hero/buttons.
# TODO(owner): create responsive display units in AdSense and paste each data-ad-slot id here.
# Never put made-up ids here. Empty id -> a placeholder box (or nothing if SHOW_EMPTY_AD_SLOTS=False).
# ---------------------------------------------------------------------------
AD_SLOT_IDS = {"H1": "", "H2": "", "H3": "", "A1": "", "A2": "", "A3": ""}
SHOW_EMPTY_AD_SLOTS = True

HOT_WINDOW = 50          # homepage hot/warm/cold + generator hot/cold lists use the last 50 draws
DEFAULT_WINDOW = "last50"

RANGE_CLASS = ["ball-r1", "ball-r2", "ball-r3", "ball-r4", "ball-r5", "ball-r6"]
HEAT_CLASS = ["heat-0", "heat-1", "heat-2", "heat-3", "heat-4"]
HEAT_LABEL = ["Cold", "Cool", "Average", "Hot", "Very hot"]
TOP_CLASS = ["top-r1", "top-r2", "top-r3", "top-r4", "top-r5", "top-r6"]

GUIDES = [
    ("lotto-max-maxmillions-explained", "How Lotto Max, MaxPlus and MaxMillions work",
     "The 2026 Lotto Max format: four selections from 1–52, $100,000 MaxPlus prizes and $1 million MaxMillions draws.", "💰"),
    ("lotto-649-gold-ball-explained", "How the Lotto 6/49 Gold Ball draw works",
     "The fixed $5 million Classic jackpot, the 30-ball Gold Ball drum, and why someone wins every draw.", "🟡"),
    ("how-to-claim-lottery-prize-bc", "How to check and claim a lottery prize in BC and Western Canada",
     "Ticket checkers, signing your ticket, ID, claim limits for BCLC and WCLC, and the one-year deadline.", "🎟️"),
    ("are-lottery-winnings-taxed-canada", "Are lottery winnings taxed in Canada?",
     "What the CRA says about prizes, the interest you earn afterwards, and common misunderstandings.", "🧾"),
    ("extra-and-encore-explained", "Extra and Encore explained",
     "The $1 add-on games: BC Extra, WCLC Extra and Ontario's Encore are different games with different odds.", "➕"),
    ("lottery-scams-canada", "Common lottery scams in Canada and how to spot them",
     "Advance-fee 'you won' messages, fake cheques, ticket-photo requests and number-selling schemes.", "🚨"),
    ("odds", "Lotto 6/49 and Lotto Max odds explained",
     "Where 1 in 13,983,816 and 1 in 33,446,140 come from, and what no system can change.", "🎲"),
    ("hot-cold-explained", "Why hot and cold numbers do not predict the next draw",
     "What a frequency table measures, and why short samples always look streaky.", "🌡️"),
    ("how-canada-lotto-works", "Who runs Lotto 6/49 and Lotto Max in Canada",
     "The Interprovincial Lottery Corporation, provincial operators and where this site fits.", "🍁"),
]

TOOLS = [
    ("/check-my-numbers.html", "Check my numbers", "🎯",
     "Run your regular line against every Lotto 6/49 draw since 1982 and every Lotto Max draw since 2009."),
    ("/lotto-max-results.html#stats", "Number stats explorer", "📊",
     "How often every number came up, hot / warm / cold groups, pairs and patterns for the last 10 to 4,000+ draws."),
    ("/lotto-odds-calculator.html", "Odds calculator", "🧮",
     "What your usual spend buys in real odds: every prize tier, a year of play and plain comparisons."),
]

NAV = [
    ("/", "Home"),
    ("/lotto-max-results.html", "Lotto Max"),
    ("/lotto-649-results.html", "Lotto 6/49"),
    ("/check-my-numbers.html", "Check my numbers"),
    ("/lotto-odds-calculator.html", "Odds calculator"),
    ("/guides.html", "Guides"),
    ("/about.html", "About"),
    ("/contact.html", "Contact"),
]

FOOTER_LEGAL = [
    ("/about.html", "About"),
    ("/contact.html", "Contact"),
    ("/privacy.html", "Privacy policy"),
    ("/terms.html", "Terms of use"),
    ("/disclaimer.html", "Disclaimer"),
    ("/responsible-play.html", "Responsible play"),
]

GAMES = {
    "lotto_max": {
        "name": "Lotto Max", "slug": "lotto-max", "short": "max",
        "path": "/lotto-max-results.html",
        "N": 52, "k": 7, "low_max": 26, "price": 6,
        "draw_weekdays": (1, 4), "draw_days": "Tuesday and Friday",
        "official": "https://www.wclc.com/winning-numbers/lotto-max-extra.htm",
        "guide": "/lotto-max-maxmillions-explained.html",
        "badge": "badge-max", "card": "card-max", "gcard": "gcard-max", "hero": "hero-max",
        # Number range changed twice. Statistics are only ever computed inside one era.
        "eras": [
            {"key": "r52", "N": 52, "low_max": 26, "start": "2026-04-14", "end": None,
             "label": "1–52 format", "long": "the current 1–52 format (since April 14, 2026)"},
            {"key": "r50", "N": 50, "low_max": 25, "start": "2019-05-14", "end": "2026-04-10",
             "label": "1–50 era", "long": "the 1–50 format (May 14, 2019 to April 10, 2026)"},
            {"key": "r49", "N": 49, "low_max": 24, "start": "2009-09-25", "end": "2019-05-10",
             "label": "1–49 era", "long": "the original 1–49 format (September 25, 2009 to May 10, 2019)"},
        ],
    },
    "lotto_649": {
        "name": "Lotto 6/49", "slug": "lotto-649", "short": "649",
        "path": "/lotto-649-results.html",
        "N": 49, "k": 6, "low_max": 24, "price": 3,
        "draw_weekdays": (2, 5), "draw_days": "Wednesday and Saturday",
        "official": "https://www.wclc.com/winning-numbers/lotto-649-extra.htm",
        "guide": "/lotto-649-gold-ball-explained.html",
        "badge": "badge-649", "card": "card-649", "gcard": "gcard-649", "hero": "hero-649",
        "eras": [
            {"key": "all", "N": 49, "low_max": 24, "start": "1982-06-12", "end": None,
             "label": "All draws", "long": "every draw since June 12, 1982"},
        ],
    },
}

# Official prize tiers and odds per play (WCLC prize tables, accessed Oct 6, 2026; same as our guides).
ODDS = {
    "lotto_max": {
        "per": "$6 play (four selections)", "any": 5.8,
        "tiers": [
            ("7 of 7", "Jackpot: win or share $10 million to $90 million", 33446140),
            ("6 of 7 + bonus", "Share of 18.50% of the Pools Fund", 4778020),
            ("6 of 7", "Share of 18.85% of the Pools Fund", 108591),
            ("5 of 7 + bonus", "Share of 12.25% of the Pools Fund", 36197),
            ("5 of 7", "Share of 27.50% of the Pools Fund", 1684),
            ("4 of 7 + bonus", "Share of 22.90% of the Pools Fund", 1010),
            ("4 of 7", "$20", 72.2),
            ("3 of 7 + bonus", "$20", 72.2),
            ("3 of 7", "Free Play", 7.0),
        ],
    },
    "lotto_649": {
        "per": "$3 play", "any": 6.6,
        "tiers": [
            ("6 of 6", "Win or share the $5 million Classic jackpot", 13983816),
            ("5 of 6 + bonus", "Share of 32.15% of the Pools Fund", 2330636),
            ("5 of 6", "Share of 13.5% of the Pools Fund", 55492),
            ("4 of 6", "Share of 54.35% of the Pools Fund", 1033),
            ("3 of 6", "$10", 56.7),
            ("2 of 6 + bonus", "$5", 81.2),
            ("2 of 6", "Free Play", 8.3),
        ],
    },
}

esc = html.escape


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def parse_date(s):
    return datetime.strptime(s, "%A, %B %d, %Y")


def long_date(dt):
    return f"{dt.strftime('%A, %B')} {dt.day}, {dt.year}"


def short_date(dt):
    return f"{dt.strftime('%a, %b')} {dt.day}, {dt.year}"


def tiny_date(dt):
    return f"{dt.strftime('%a, %b')} {dt.day}"


def month_year(dt):
    return dt.strftime("%B %Y")


def clock(dt):
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d} {'PM' if dt.hour >= 12 else 'AM'}"


def money(n):
    if n is None:
        return "—"
    if n >= 1_000_000 and n % 1_000_000 == 0:
        return f"${n // 1_000_000} million"
    return f"${n:,}"


def money_short(n):
    if n is None:
        return "—"
    if n >= 1_000_000 and n % 1_000_000 == 0:
        return f"${n // 1_000_000}M"
    return f"${n:,}"


def comb(n, k):
    return math.comb(n, k)


def pct(x):
    return f"{x * 100:.1f}%"


def fmt_odds(x):
    return f"{x:,.0f}" if x >= 100 else f"{x:.1f}"


def plural(n, word, many=None):
    return f"{n:,} {word if n == 1 else (many or word + 's')}"


def write_file(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def range_class(n):
    return RANGE_CLASS[min((n - 1) // 10, 5)]


def heat_index(z, count):
    if count == 0 or z <= -1.5:
        return 0
    if z <= -0.5:
        return 1
    if z < 0.5:
        return 2
    if z < 1.5:
        return 3
    return 4


# ---------------------------------------------------------------------------
# Balls
# ---------------------------------------------------------------------------
def ball(n, size="sm", anim=None, extra=""):
    cls = f"ball ball-{size} {range_class(n)}"
    if extra:
        cls += " " + extra
    style = ""
    if anim is not None:
        cls += " roll"
        style = f' style="--i:{anim}"'
    inner = f"<span>{n}</span>" if size == "lg" else str(n)
    return f'<span class="{cls}"{style}>{inner}</span>'


def bonus_ball(n, size="sm", anim=None, extra=""):
    cls = f"ball ball-{size} ball-bonus"
    if extra:
        cls += " " + extra
    style = ""
    if anim is not None:
        cls += " roll"
        style = f' style="--i:{anim}"'
    inner = f"<span>{n}</span>" if size == "lg" else str(n)
    return f'<span class="{cls}" title="Bonus number"{style}>{inner}</span>'


def balls_row(numbers, bonus=None, size="sm", animate=False, caption=False):
    parts = [ball(n, size, i if animate else None) for i, n in enumerate(numbers)]
    if bonus is not None:
        parts.append('<span class="plus" aria-hidden="true">+</span>')
        b = bonus_ball(bonus, size, len(numbers) if animate else None)
        if caption:
            b = f'<span class="bonus-wrap">{b}<span class="bonus-cap">BONUS</span></span>'
        parts.append(b)
    label = ", ".join(str(n) for n in numbers) + (f", bonus {bonus}" if bonus is not None else "")
    return f'<span class="balls balls-{size}" role="img" aria-label="{esc(label)}">{"".join(parts)}</span>'


def gold_icon(kind):
    if kind == "Gold":
        return '<span class="ball ball-xs ball-gold" aria-hidden="true">G</span>'
    return '<span class="ball ball-xs ball-white" aria-hidden="true">W</span>'


# ---------------------------------------------------------------------------
# Records, eras and statistics
# ---------------------------------------------------------------------------
def prep_records(records):
    out = []
    for r in records:
        dt = parse_date(r["date"])
        d = dict(r)
        d["dt"] = dt
        d["iso"] = dt.strftime("%Y-%m-%d")
        out.append(d)
    out.sort(key=lambda r: r["iso"])
    return out


def era_records(recs, era):
    return [r for r in recs if r["iso"] >= era["start"] and (era["end"] is None or r["iso"] <= era["end"])]


_SUM_CACHE = {}


def sum_distribution(N, k):
    """Exact probability of every possible sum of k distinct numbers from 1..N."""
    key = (N, k)
    if key in _SUM_CACHE:
        return _SUM_CACHE[key]
    maxs = sum(range(N - k + 1, N + 1))
    ways = [[0] * (maxs + 1) for _ in range(k + 1)]
    ways[0][0] = 1
    for n in range(1, N + 1):
        for j in range(min(k, n), 0, -1):
            row, prev = ways[j], ways[j - 1]
            for s in range(maxs, n - 1, -1):
                v = prev[s - n]
                if v:
                    row[s] += v
    total = comb(N, k)
    dist = [w / total for w in ways[k]]
    _SUM_CACHE[key] = dist
    return dist


def window_stats(recs, era_recs, N, k, low_max):
    draws = len(recs)
    counts = [0] * (N + 1)
    bonus_counts = [0] * (N + 1)
    pairs = Counter()
    odd_obs = [0] * (k + 1)
    low_obs = [0] * (k + 1)
    sums = []
    consec = 0
    for r in recs:
        nums = sorted(r["numbers"])
        for x in nums:
            counts[x] += 1
        b = r.get("bonus")
        if isinstance(b, int) and 1 <= b <= N:
            bonus_counts[b] += 1
        pairs.update(combinations(nums, 2))
        odd_obs[sum(1 for x in nums if x % 2)] += 1
        low_obs[sum(1 for x in nums if x <= low_max)] += 1
        sums.append(sum(nums))
        if any(b2 - a == 1 for a, b2 in zip(nums, nums[1:])):
            consec += 1
    last = {}
    for idx, r in enumerate(era_recs):
        for x in r["numbers"]:
            last[x] = idx
    E = len(era_recs)
    since = [None] * (N + 1)
    for i in range(1, N + 1):
        since[i] = (E - 1 - last[i]) if i in last else None
    p = k / N
    expected = draws * p
    sd = math.sqrt(draws * p * (1 - p)) if draws else 0.0
    z = [0.0] * (N + 1)
    heat = [0] * (N + 1)
    for i in range(1, N + 1):
        z[i] = (counts[i] - expected) / sd if sd else 0.0
        heat[i] = heat_index(z[i], counts[i])
    lo, hi = expected - 2 * sd, expected + 2 * sd
    nums = list(range(1, N + 1))
    outside = [i for i in nums if counts[i] < lo or counts[i] > hi]
    total = comb(N, k)
    odd_total, even_total = (N + 1) // 2, N // 2
    odd_rows = [(j, k - j, odd_obs[j], comb(odd_total, j) * comb(even_total, k - j) / total) for j in range(k + 1)]
    low_rows = [(j, k - j, low_obs[j], comb(low_max, j) * comb(N - low_max, k - j) / total) for j in range(k + 1)]
    big = 10 ** 9
    hot_rank = sorted(nums, key=lambda i: (-counts[i], since[i] if since[i] is not None else big, i))
    cold_rank = sorted(nums, key=lambda i: (counts[i], -(since[i] if since[i] is not None else big), i))
    return {
        "draws": draws, "N": N, "k": k, "low_max": low_max,
        "first": recs[0]["dt"] if recs else None, "last": recs[-1]["dt"] if recs else None,
        "counts": counts, "bonus_counts": bonus_counts, "since": since, "z": z, "heat": heat,
        "expected": expected, "sd": sd, "lo": lo, "hi": hi, "outside": outside,
        "odd_rows": odd_rows, "low_rows": low_rows, "sums": sums,
        "sum_min": min(sums) if sums else None, "sum_max": max(sums) if sums else None,
        "sum_mean": (sum(sums) / len(sums)) if sums else None, "sum_theory": k * (N + 1) / 2,
        "consec_obs": consec, "consec_prob": 1 - comb(N - k + 1, k) / total,
        "pair_expected": draws * k * (k - 1) / (N * (N - 1)),
        "top_pairs": sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))[:10],
        "hot": hot_rank[:6], "warm": hot_rank[6:12], "cold": cold_rank[:6],
        "hot12": hot_rank[:12], "cold12": cold_rank[:12],
    }


def stat_windows(game_key, recs):
    """The window picker options. Lotto Max windows never mix number ranges."""
    cfg = GAMES[game_key]
    eras = cfg["eras"]
    cur_era = eras[0]
    cur = era_records(recs, cur_era)
    k = cfg["k"]
    out = []

    def add(key, tab, desc, rs, era_rs, era, live):
        if not rs:
            return
        out.append({"key": key, "tab": tab, "desc": desc, "era": era, "live": live,
                    "st": window_stats(rs, era_rs, era["N"], k, era["low_max"])})

    add("last10", "Last 10", "the last 10 draws", cur[-10:], cur, cur_era, True)
    add("last50", "Last 50", "the last 50 draws", cur[-50:], cur, cur_era, True)
    if game_key == "lotto_649":
        add("last100", "Last 100", "the last 100 draws", cur[-100:], cur, cur_era, True)
        add("all", f"All {len(cur):,}", f"all {len(cur):,} draws since June 12, 1982", cur, cur, cur_era, True)
    else:
        add("r52", f"All 1–52 ({len(cur)})", f"all {len(cur)} draws in the current 1–52 format", cur, cur, cur_era, True)
        for era in eras[1:]:
            rs = era_records(recs, era)
            add(era["key"], f"{era['label']} ({len(rs)})", f"all {len(rs)} draws in {era['long']}", rs, rs, era, False)
    return out


def gold_ball_derivation(records):
    """Gold Ball jackpot for each record (same order), derived only from published results and
    WCLC's rule ($10M after a gold-ball win, +$2M after every white ball). None where unknown."""
    n = len(records)
    jp = [None] * n
    for i, r in enumerate(records):
        gb = r.get("gold_ball") or {}
        if r.get("gold_ball_jackpot"):
            jp[i] = r["gold_ball_jackpot"]
        if gb.get("ball") == "Gold" and gb.get("prize"):
            jp[i] = gb["prize"]
    for i in range(1, n):
        if jp[i] is not None:
            continue
        prev = records[i - 1].get("gold_ball") or {}
        if prev.get("ball") == "Gold":
            jp[i] = GOLD_BALL_START
        elif prev.get("ball") == "White" and jp[i - 1] is not None:
            jp[i] = jp[i - 1] + GOLD_BALL_STEP
    for i in range(n - 2, -1, -1):
        if jp[i] is not None:
            continue
        gb = records[i].get("gold_ball") or {}
        if gb.get("ball") == "White" and jp[i + 1] is not None and jp[i + 1] > GOLD_BALL_START:
            jp[i] = jp[i + 1] - GOLD_BALL_STEP
    return jp


def expected_latest_draw(today, weekdays):
    d = today.date() - timedelta(days=1)
    while d.weekday() not in weekdays:
        d -= timedelta(days=1)
    return d


def next_draw_info(game_key, history, today):
    """Next draw date + countdown target. Jackpot info only if WCLC's ticker is for that draw."""
    cfg = GAMES[game_key]
    up = (history.get("upcoming") or {}).get(game_key) or {}
    today_iso = today.strftime("%Y-%m-%d")
    if up.get("date") and up["date"] >= today_iso:
        d = date.fromisoformat(up["date"])
        info = up
    else:
        d = today.date()
        while d.weekday() not in cfg["draw_weekdays"]:
            d += timedelta(days=1)
        info = {}
    t_et = datetime(d.year, d.month, d.day, DRAW_TIME_ET[0], DRAW_TIME_ET[1], tzinfo=ET)
    t_pt = t_et.astimezone(PT)
    return {
        "date": d, "up": info,
        "utc": t_et.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "label": f"{t_pt.strftime('%a, %b')} {t_pt.day} · {clock(t_pt)} PT",
    }


def countdown(nd):
    return f'<span class="cd" data-target="{nd["utc"]}"></span>'


def last_check_label(history):
    meta = history.get("meta") or {}
    lc = meta.get("last_checked")
    if lc:
        try:
            dt = datetime.fromisoformat(lc).astimezone(PT)
            return f"last check {dt.strftime('%a, %b')} {dt.day}, {clock(dt)} PT"
        except ValueError:
            pass
    fetched = [(history.get("upcoming") or {}).get(g, {}).get("fetched") for g in GAMES]
    fetched = [f for f in fetched if f]
    if fetched:
        d = datetime.strptime(max(fetched), "%Y-%m-%d")
        return f"last check {d.strftime('%a, %b')} {d.day}, {d.year}"
    return "checked nightly"


# ---------------------------------------------------------------------------
# Jackpot snapshots (advertised jackpot per draw, recorded from WCLC's ticker)
# ---------------------------------------------------------------------------
def update_jackpot_history(history, prep):
    data = {"lotto_max": {}, "lotto_649": {}}
    if os.path.exists(JACKPOT_FILE):
        try:
            with open(JACKPOT_FILE, encoding="utf-8") as f:
                loaded = json.load(f)
            for g in data:
                data[g].update(loaded.get(g) or {})
        except Exception:
            pass
    for r in prep["lotto_max"]:
        if r.get("jackpot"):
            e = data["lotto_max"].setdefault(r["iso"], {})
            e.setdefault("jackpot", r["jackpot"])
            for f in ("maxmillions", "maxplus"):
                if r.get(f) is not None:
                    e.setdefault(f, r[f])
    for r in prep["lotto_649"]:
        if r.get("gold_ball_jackpot"):
            data["lotto_649"].setdefault(r["iso"], {}).setdefault("gold_ball_jackpot", r["gold_ball_jackpot"])
    fields = {"lotto_max": ("jackpot", "maxmillions", "maxplus"), "lotto_649": ("gold_ball_jackpot", "balls_remaining")}
    for g, flist in fields.items():
        up = (history.get("upcoming") or {}).get(g) or {}
        if not up.get("date"):
            continue
        e = data[g].setdefault(up["date"], {})
        for f in flist:
            if up.get(f) is not None:
                e[f] = up[f]
        fetched = up.get("fetched")
        if fetched:
            e["first_seen"] = min(e.get("first_seen") or fetched, fetched)
            e["last_seen"] = max(e.get("last_seen") or fetched, fetched)
    out = {g: {k: data[g][k] for k in sorted(data[g])} for g in data}
    with open(JACKPOT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    return out


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
def ad_slot(key):
    slot = AD_SLOT_IDS.get(key) or ""
    if slot:
        return ('<aside class="ad-slot" aria-label="Advertisement"><p class="ad-label">Advertisement</p>'
                f'<ins class="adsbygoogle" style="display:block" data-ad-client="{ADSENSE_CLIENT}" data-ad-slot="{esc(slot)}" '
                'data-ad-format="auto" data-full-width-responsive="true"></ins>'
                '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script></aside>')
    todo = (f"<!-- TODO(owner): ad slot {key}. Create a responsive display unit in AdSense and put its "
            f"data-ad-slot id in AD_SLOT_IDS['{key}'] in build.py (no made-up ids). -->")
    if not SHOW_EMPTY_AD_SLOTS:
        return todo
    return f'<aside class="ad-slot" aria-label="Advertisement" data-slot="{key}">{todo}<p class="ad-label">Advertisement</p></aside>'


def nav_links(active, cls):
    out = []
    for href, label in NAV:
        c = cls + (" nav-active" if href == active else "")
        cur = ' aria-current="page"' if href == active else ""
        out.append(f'<a href="{href}" class="{c.strip()}"{cur}>{esc(label)}</a>')
    return "".join(out)


def footer_html():
    legal = " · ".join(f'<a href="{h}">{esc(t)}</a>' for h, t in FOOTER_LEGAL)
    guides = "".join(f'<li><a href="/{g[0]}.html">{esc(g[1])}</a></li>' for g in GUIDES)
    tools = "".join(f'<li><a href="{t[0]}">{esc(t[1])}</a></li>' for t in TOOLS)
    return f"""<footer class="site-footer">
  <div class="wrap py-10 grid gap-8 md:grid-cols-2 lg:grid-cols-4">
    <div class="space-y-2">
      <p class="fh">lottohelper.ca</p>
      <p>An independent, unofficial reference for Lotto Max and Lotto 6/49 results, number statistics and plain-language guides. Run by NextGen from British Columbia, Canada.</p>
      <p>Not affiliated with BCLC, WCLC, OLG, Loto-Québec, Atlantic Lottery or the Interprovincial Lottery Corporation. We do not sell tickets or predict draws. 19+ in most provinces (18+ in Alberta, Manitoba and Quebec).</p>
    </div>
    <div>
      <p class="fh">Results &amp; tools</p>
      <ul class="space-y-1">
        <li><a href="/lotto-max-results.html">Lotto Max results &amp; stats</a></li>
        <li><a href="/lotto-649-results.html">Lotto 6/49 results &amp; stats</a></li>
        {tools}
      </ul>
    </div>
    <div>
      <p class="fh">Guides</p>
      <ul class="space-y-1"><li><a href="/guides.html">All guides</a></li>{guides}</ul>
    </div>
    <div>
      <p class="fh">Site information</p>
      <p class="leading-7">{legal}</p>
      <p class="mt-4">Official results and prize claims: your provincial lottery corporation. If anything here disagrees with an official source, the official source is correct.</p>
      <p class="mt-4">© 2026 lottohelper.ca</p>
    </div>
  </div>
</footer>"""


def layout(path, title, description, body, active=None, noindex=False, scripts=()):
    full_title = f"{title} | {SITE_NAME}" if path != "/" else title
    canonical = SITE + path
    robots = '<meta name="robots" content="noindex">\n  ' if noindex else ""
    canonical_tag = "" if noindex else f'<link rel="canonical" href="{canonical}">\n  '
    act = active if active is not None else path
    script_tags = "".join(f'\n  <script src="{s}" defer></script>' for s in scripts)
    return f"""<!DOCTYPE html>
<html lang="en-CA">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(full_title)}</title>
  <meta name="description" content="{esc(description)}">
  {robots}{canonical_tag}<meta name="theme-color" content="#0B1033">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="{SITE_NAME}">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:url" content="{canonical}">
  <link rel="preload" href="{FONT_HREF}" as="font" type="font/woff2" crossorigin>
  <link rel="stylesheet" href="{CSS_HREF}">
  {ADSENSE_TAG}{script_tags}
</head>
<body class="antialiased">
  <a href="#main" class="skip">Skip to content</a>
  <div class="topbar">19+ · Unofficial independent site · Not BCLC, WCLC, OLG, Loto-Québec or ILC · We do not sell tickets · <a href="/responsible-play.html">Play responsibly</a></div>
  <header class="site-header">
    <div class="wrap bar">
      <a href="/" class="logo" aria-label="lottohelper.ca home"><span class="logo-badge">LOTTOHELPER.CA</span>
        <span class="logo-dots hidden sm:inline-flex" aria-hidden="true"><i style="background:#FACC15"></i><i style="background:#2563EB"></i><i style="background:#DC2626"></i><i style="background:#15803D"></i><i style="background:#7C3AED"></i></span></a>
      <nav class="nav-desk" aria-label="Main">{nav_links(act, "nav-link")}</nav>
      <details class="menu"><summary aria-label="Open menu">☰ Menu</summary>
        <nav class="menu-panel" aria-label="Main (mobile)">{nav_links(act, "")}<a href="/responsible-play.html">Responsible play</a></nav>
      </details>
    </div>
  </header>
  <main id="main">
{body}
  </main>
{footer_html()}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Content pages (content/*.html)
# ---------------------------------------------------------------------------
META_RE = re.compile(r"^\s*<!--meta\s*(\{.*?\})\s*-->", re.S)


def load_content_pages():
    pages = []
    for name in sorted(os.listdir(CONTENT_DIR)):
        if not name.endswith(".html"):
            continue
        with open(os.path.join(CONTENT_DIR, name), encoding="utf-8") as f:
            raw = f.read()
        m = META_RE.match(raw)
        if not m:
            raise ValueError(f"{name}: missing <!--meta {{...}} --> header")
        meta = json.loads(m.group(1))
        body = raw[m.end():].strip()
        pages.append((name[:-5], meta, body))
    return pages


def guide_byline(meta):
    updated = meta.get("updated", "October 2026")
    return f'<p class="byline">Written by NextGen, British Columbia · Last updated {esc(updated)}</p>'


def related_guides(slug):
    items = [g for g in GUIDES if g[0] != slug][:5]
    lis = "".join(f'<li><a href="/{g[0]}.html">{g[3]} {esc(g[1])}</a></li>' for g in items)
    return (f'<aside class="card card-violet mt-8"><h2 class="section-title mb-2">More guides</h2>'
            f'<ul class="space-y-2">{lis}</ul>'
            f'<p class="mt-3 text-sm"><a href="/guides.html">See all guides →</a> · <a href="/check-my-numbers.html">Check my numbers</a> · <a href="/lotto-odds-calculator.html">Odds calculator</a></p></aside>')


def render_content_page(slug, meta, body):
    if meta.get("kind") == "guide":
        body = body.replace("</h1>", "</h1>\n" + guide_byline(meta), 1)
        inner = f'<article class="card card-violet prose-lh">{body}</article>{related_guides(slug)}'
    else:
        inner = f'<article class="card card-violet prose-lh">{body}</article>'
    path = f"/{slug}.html"
    page = f'<div class="wrap py-8"><div class="max-w-3xl mx-auto">{inner}</div></div>'
    return layout(path, meta["title"], meta["description"], page, active=meta.get("nav", path))


def guide_cards(heading_tag="h3"):
    cards = []
    for i, (s, t, d, icon) in enumerate(GUIDES):
        top = TOP_CLASS[i % len(TOP_CLASS)]
        cards.append(f'<a href="/{s}.html" class="card lift {top}"><span class="text-2xl" aria-hidden="true">{icon}</span>'
                     f'<{heading_tag} class="font-display font-bold text-lg text-slate-900 leading-snug mt-1">{esc(t)}</{heading_tag}>'
                     f'<p class="text-sm muted mt-1">{esc(d)}</p></a>')
    return "".join(cards)


def render_guides_index():
    body = f"""<div class="wrap py-8">
<section class="card card-violet prose-lh max-w-3xl mx-auto">
<h1>Guides</h1>
<p class="byline">Written by NextGen, British Columbia · Last updated October 2026</p>
<p>These guides explain how Canada's national lotto games actually work: what you are buying, how prizes are paid, how to claim, what is taxed, and how to avoid the scams that circulate after every big jackpot. They are written for players in British Columbia and Western Canada first, with notes where Ontario, Quebec or Atlantic Canada differ.</p>
<p>Every factual claim is checked against the operator or government page linked inside each guide (BCLC, WCLC, OLG, the Canada Revenue Agency or the Canadian Anti-Fraud Centre). Game rules change — Lotto Max changed format in April 2026 — so when a guide and an official page disagree, follow the official page and <a href="/contact.html">tell us</a> so we can fix it.</p>
<p>None of these guides will tell you which numbers to pick. No guide can: every draw is independent, and the odds on a ticket are fixed by the game design.</p>
</section>
<section class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 mt-8">{guide_cards("h2")}</section>
</div>"""
    return layout("/guides.html", "Lotto guides for Canadian players",
                  "Plain-language guides to Lotto Max, Lotto 6/49, Gold Ball, MaxMillions, Extra, Encore, prize claims in BC, taxes and lottery scams in Canada.",
                  body, active="/guides.html")


def render_404():
    body = """<div class="wrap py-10"><section class="card card-violet prose-lh text-center max-w-2xl mx-auto">
<p class="text-4xl" aria-hidden="true">🎱</p>
<h1>Page not found</h1>
<p>The page you asked for is not here. Older per-draw pages were merged into two results archives in October 2026, so a bookmarked link may have moved.</p>
<p><a href="/lotto-max-results.html">Lotto Max results</a> · <a href="/lotto-649-results.html">Lotto 6/49 results</a> · <a href="/check-my-numbers.html">Check my numbers</a> · <a href="/guides.html">Guides</a> · <a href="/">Home</a></p>
<p>If you followed a broken link on this site, please let us know through the <a href="/contact.html">contact page</a>.</p>
</section></div>"""
    return layout("/404.html", "Page not found", "This page could not be found on lottohelper.ca.", body,
                  active="", noindex=True)


# ---------------------------------------------------------------------------
# Shared widgets
# ---------------------------------------------------------------------------
def hwc_strip(st, light=False):
    """Hot / warm / cold groups for one stats window (🔥 ⚡ ❄️)."""
    def group(nums):
        return "".join(f'<span class="hb">{ball(n, "xs")}<span class="hb-n">{st["counts"][n]}×</span></span>' for n in nums)
    color = ("text-red-700", "text-amber-700", "text-sky-700") if light else ("text-red-300", "text-amber-200", "text-sky-200")
    rows = [
        ("🔥 Hot", color[0], st["hot"]),
        ("⚡ Warm", color[1], st["warm"]),
        ("❄️ Cold", color[2], st["cold"]),
    ]
    out = "".join(f'<div class="hwc-row"><span class="hwc-tag {c}">{t}</span><span class="balls balls-xs">{group(ns)}</span></div>' for t, c, ns in rows)
    return f'<div class="{"light" if light else ""}">{out}</div>'


def maxmillions_meter(jp, light=True):
    jp = jp or MAX_JACKPOT_START
    pct_fill = max(0, min(100, (jp - MAX_JACKPOT_START) / (MAX_JACKPOT_CAP - MAX_JACKPOT_START) * 100))
    mm_left = (MAXMILLIONS_FROM - MAX_JACKPOT_START) / (MAX_JACKPOT_CAP - MAX_JACKPOT_START) * 100
    return (f'<div class="meter" role="img" aria-label="Jackpot {money(jp)} on a scale from $10 million to the $90 million cap">'
            f'<div class="meter-fill" style="width:{pct_fill:.1f}%"></div>'
            f'<div class="meter-mk start" style="left:0"><span>$10M</span></div>'
            f'<div class="meter-mk" style="left:{mm_left:.1f}%"><span>$50M · MaxMillions</span></div>'
            f'<div class="meter-mk end" style="left:calc(100% - 2px)"><span>$90M cap</span></div></div>')


def gold_drum(balls_left):
    balls_left = max(1, min(GOLD_BALL_BALLS, balls_left or GOLD_BALL_BALLS))
    gone = GOLD_BALL_BALLS - balls_left
    cells = ['<i class="gone"></i>'] * gone + ["<i></i>"] * (balls_left - 1) + ['<i class="q"></i>']
    return (f'<div class="drum" role="img" aria-label="{balls_left} balls left in the Gold Ball drum: {balls_left - 1} white and 1 gold">'
            + "".join(cells) + "</div>")


def spark(points, fmt=money_short):
    """points: list of (label, value). Simple bar sparkline, newest on the right."""
    if not points:
        return ""
    top = max(v for _, v in points) or 1
    bars = "".join(f'<div title="{esc(l)}: {money(v)}"><small>{fmt(v)}</small><span class="sb" style="height:{max(4, v / top * 100):.0f}%"></span><small>{esc(l)}</small></div>'
                   for l, v in points)
    return f'<div class="spark">{bars}</div>'


def next_draw_block(game_key, nd, dark=True):
    cfg = GAMES[game_key]
    up = nd["up"]
    if game_key == "lotto_max":
        jp = up.get("jackpot")
        main = (f'<p class="jp-label">Next jackpot · {esc(tiny_date(datetime.combine(nd["date"], datetime.min.time())))}</p>'
                f'<p class="jackpot mt-1" data-count="{jp}">{money_short(jp)}</p>') if jp else (
                f'<p class="jp-label">Next draw</p><p class="jackpot mt-1 text-3xl">{esc(tiny_date(datetime.combine(nd["date"], datetime.min.time())))}</p>')
        chips = []
        if up.get("maxmillions"):
            chips.append(f'<span class="chip chip-gold">💰 {up["maxmillions"]} × $1M MaxMillions</span>')
        if up.get("maxplus"):
            chips.append(f'<span class="chip">➕ {up["maxplus"]} × $100K MaxPlus</span>')
    else:
        jp = up.get("gold_ball_jackpot")
        main = (f'<p class="jp-label">Gold Ball jackpot · {esc(tiny_date(datetime.combine(nd["date"], datetime.min.time())))}</p>'
                f'<p class="jackpot mt-1" data-count="{jp}">{money_short(jp)}</p>') if jp else (
                f'<p class="jp-label">Next draw</p><p class="jackpot mt-1 text-3xl">{esc(tiny_date(datetime.combine(nd["date"], datetime.min.time())))}</p>')
        chips = ['<span class="chip">🎯 $5M Classic jackpot</span>']
        if up.get("balls_remaining"):
            chips.append(f'<span class="chip chip-gold">🟡 {up["balls_remaining"]} balls left · 1 in {up["balls_remaining"]}</span>')
    chips.append(f'<span class="chip">⏱ {countdown_inline(nd)}</span>')
    return main + f'<div class="chips mt-3">{"".join(chips)}</div>'


def countdown_inline(nd):
    return f'<span class="cd" data-target="{nd["utc"]}">{esc(nd["label"])}</span>'


def latest_block(game_key, rec, size="lg", animate=True):
    gb = ""
    if game_key == "lotto_649" and rec.get("gold_ball"):
        g = rec["gold_ball"]
        what = "Gold ball" if g.get("ball") == "Gold" else "White ball"
        gb = f'<p class="text-sm mt-2 sub">{gold_icon(g.get("ball"))} Gold Ball draw: {what} · {money(g.get("prize"))} prize</p>'
    return (f'<p class="jp-label">Latest result · {esc(short_date(rec["dt"]))}</p>'
            f'<div class="mt-2">{balls_row(rec["numbers"], rec.get("bonus"), size, animate, caption=(size == "lg"))}</div>{gb}')


def generator_panel(prep_cur):
    """Lucky Numbers Generator — just for fun. Data for both games precomputed into attributes."""
    attrs = []
    for gk in ("lotto_max", "lotto_649"):
        cfg = GAMES[gk]
        st = prep_cur[gk]
        attrs.append(f'data-{cfg["short"]}="{cfg["eras"][0]["N"]},{cfg["k"]},{"-".join(map(str, st["hot12"]))},{"-".join(map(str, st["cold12"]))}"')
    blanks = "".join(f'<span class="ball ball-md ball-blank">?</span>' for _ in range(7))
    return f"""<section class="glass p-4 sm:p-5" id="generator" aria-labelledby="gen-h" {" ".join(attrs)}>
  <div class="flex flex-wrap items-center justify-between gap-3">
    <h2 id="gen-h" class="font-display font-extrabold text-xl text-white">🎲 Lucky Numbers Generator — just for fun</h2>
    <div class="seg seg-dark" role="group" aria-label="Game"><button type="button" data-game="max" aria-pressed="true">Lotto Max</button><button type="button" data-game="649" aria-pressed="false">Lotto 6/49</button></div>
  </div>
  <div class="gen-out mt-3" aria-live="polite"><span class="balls balls-md" data-gen-out>{blanks}</span></div>
  <div class="flex flex-wrap items-center gap-3 mt-3">
    <button type="button" class="btn-gold" data-gen-go>Roll a random line</button>
    <a class="btn-ghost" data-gen-check href="/check-my-numbers.html">Check this line against history</a>
  </div>
  <details class="gen-opts mt-3"><summary>Options</summary>
    <div class="grid gap-3 sm:grid-cols-2 mt-2 text-indigo-100">
      <label class="field">Odd / even mix<select data-opt="oe"><option value="any">Any mix</option><option value="bal">Balanced (3–4 odd)</option><option value="odd">Mostly odd</option><option value="even">Mostly even</option></select></label>
      <label class="field">Hot / cold mix (last 50 draws)<select data-opt="hc"><option value="any">Ignore stats</option><option value="hot">Lean on hot numbers</option><option value="cold">Lean on cold numbers</option><option value="mix">Half hot, half cold</option></select></label>
      <label class="field">Always include (comma-separated)<input type="text" inputmode="numeric" data-opt="inc" placeholder="e.g. 7, 21"></label>
      <label class="field">Never include<input type="text" inputmode="numeric" data-opt="exc" placeholder="e.g. 13"></label>
      <label class="check sm:col-span-2"><input type="checkbox" data-opt="pop" checked> Avoid popular patterns (all birthdays ≤31, runs like 5-6-7, evenly spaced lines) — fewer people to share a jackpot with</label>
    </div>
  </details>
  <p class="text-xs text-indigo-200 mt-3">Random picks for entertainment. They don't predict draws; every combination has the same odds.</p>
</section>"""


def my_line_slot(prep):
    attrs = []
    for gk in ("lotto_max", "lotto_649"):
        cfg = GAMES[gk]
        r = prep[gk][-1]
        attrs.append(f'data-{cfg["short"]}="{r["iso"]}|{"-".join(map(str, r["numbers"]))}|{r.get("bonus") or ""}"')
    return (f'<section class="glass p-4 mt-4" id="my-line" {" ".join(attrs)} style="min-height:92px">'
            '<p class="jp-label">Your numbers vs the latest draw</p>'
            '<div data-myline class="mt-2 text-sm text-indigo-100">Save your regular line on <a href="/check-my-numbers.html">Check my numbers</a> and it will show up here after every draw, matched against the latest result. It stays in this browser only.</div>'
            '</section>')


# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------
def home_game_card(game_key, prep, nd, st):
    cfg = GAMES[game_key]
    rec = prep[game_key][-1]
    note = ""
    return f"""<article class="glass gcard {cfg['gcard']}">
  <div class="flex items-center justify-between gap-2"><span class="badge {cfg['badge']}">{cfg['name']}</span><span class="text-xs text-indigo-200">{cfg['draw_days']} · 7:30 PM PT</span></div>
  <div class="mt-3">{next_draw_block(game_key, nd)}</div>
  <div class="mt-4">{latest_block(game_key, rec)}</div>{note}
  <div class="mt-4"><p class="jp-label mb-1">Last {HOT_WINDOW} draws</p>{hwc_strip(st)}</div>
  <p class="mt-3 text-sm"><a href="{cfg['path']}">All {cfg['name']} results &amp; stats →</a></p>
</article>"""


def recent_rows(game_key, recs, n=6):
    rows = []
    for r in reversed(recs[-n:]):
        extra = ""
        if game_key == "lotto_max" and r.get("jackpot"):
            extra = f'<span class="text-xs muted">jackpot {money_short(r["jackpot"])}</span>'
        if game_key == "lotto_649" and r.get("gold_ball"):
            extra = f'<span class="gb-ico text-xs muted">{gold_icon(r["gold_ball"].get("ball"))}</span>'
        rows.append(f'<li><span class="dt">{esc(short_date(r["dt"]))}</span>{balls_row(r["numbers"], r.get("bonus"), "sm")}{extra}</li>')
    return f'<ul class="rowz">{"".join(rows)}</ul>'


def max_tracker_card(prep, history, jhist, nd):
    up = nd["up"]
    jp = up.get("jackpot") or (prep["lotto_max"][-1].get("jackpot"))
    mm = up.get("maxmillions")
    pts = [(datetime.strptime(d, "%Y-%m-%d").strftime("%b %d").replace(" 0", " "), e["jackpot"])
           for d, e in sorted((jhist.get("lotto_max") or {}).items()) if e.get("jackpot")][-12:]
    if len(pts) >= 4:
        spark_html = spark(pts)
    elif pts:
        spark_html = '<p class="text-sm mt-2">Recorded so far: ' + " → ".join(f"{esc(l)} <strong>{money_short(v)}</strong>" for l, v in pts) + "</p>"
    else:
        spark_html = ""
    note = "Jackpot snapshots are recorded each draw since October 2026, so this chart fills in over time."
    mm_txt = (f"<strong>{mm}</strong> MaxMillions prizes of $1 million each are offered." if mm else
              "MaxMillions prizes are added once the jackpot passes $50 million.")
    return f"""<article class="card card-max">
  <p class="kicker">Jackpot tracker</p>
  <h3 class="section-title mt-1">💰 Lotto Max jackpot &amp; MaxMillions</h3>
  <p class="mt-2">Next draw: <strong>{money(jp) if jp else "not announced yet"}</strong>. {mm_txt}</p>
  {maxmillions_meter(jp)}
  {spark_html}
  <p class="text-xs muted mt-2">{note} Figures are WCLC's advertised amounts before each draw and can change.</p>
</article>"""


def gold_tracker_card(prep, nd):
    up = nd["up"]
    left = up.get("balls_remaining")
    jp = up.get("gold_ball_jackpot")
    recs = prep["lotto_649"]
    derived = gold_ball_derivation(recs)
    pts = [(r["dt"].strftime("%b %d").replace(" 0", " "), v) for r, v in zip(recs, derived) if v][-12:]
    odds_txt = f"1 in {left}" if left else "—"
    return f"""<article class="card card-649">
  <p class="kicker">Gold Ball tracker</p>
  <h3 class="section-title mt-1">🟡 Lotto 6/49 Gold Ball drum</h3>
  <p class="mt-2">Gold Ball jackpot: <strong>{money(jp) if jp else "—"}</strong>. Balls left in the drum: <strong>{left or "—"}</strong>, so the chance the gold ball comes out next draw is <strong>{odds_txt}</strong>. Every white ball drawn adds $2 million and removes one ball.</p>
  <div class="mt-3">{gold_drum(left)}</div>
  {spark(pts) if len(pts) >= 2 else ""}
  <p class="text-xs muted mt-2">The drum always pays someone: a white ball means a guaranteed $1 million winner. See the <a href="/lotto-649-gold-ball-explained.html">Gold Ball guide</a>.</p>
</article>"""


def odds_band():
    return """<section class="hero hero-tool mt-10">
  <div class="wrap py-8 grid gap-6 md:grid-cols-3 items-center">
    <div class="md:col-span-1">
      <p class="jp-label">Reality check</p>
      <h2 class="font-display font-extrabold text-2xl text-white mt-1">The odds, in plain numbers</h2>
      <p class="sub text-sm mt-2">Charts can be fun. They cannot move these figures, which are fixed by the game design.</p>
    </div>
    <div class="glass p-4"><p class="jp-label">Lotto Max jackpot · per $6 play</p><p class="jackpot text-4xl mt-1">1 in 33,446,140</p><p class="text-sm sub mt-1">Any prize: about 1 in 5.8</p></div>
    <div class="glass p-4"><p class="jp-label">Lotto 6/49 jackpot · per $3 play</p><p class="jackpot text-4xl mt-1">1 in 13,983,816</p><p class="text-sm sub mt-1">Any prize: about 1 in 6.6</p></div>
    <p class="md:col-span-3 text-sm"><a href="/lotto-odds-calculator.html" class="btn-gold">🧮 Work out your own odds</a></p>
  </div>
</section>"""


def tool_cards(heading_tag="h3"):
    out = []
    for i, (href, t, icon, d) in enumerate(TOOLS):
        out.append(f'<a href="{href}" class="card lift {TOP_CLASS[(i * 2 + 1) % 6]}"><span class="text-3xl" aria-hidden="true">{icon}</span>'
                   f'<{heading_tag} class="font-display font-bold text-xl text-slate-900 mt-1">{esc(t)}</{heading_tag}><p class="text-sm muted mt-1">{esc(d)}</p></a>')
    return "".join(out)


def render_index(history, prep, today, jhist):
    nds = {g: next_draw_info(g, history, today) for g in GAMES}
    cur = {g: era_records(prep[g], GAMES[g]["eras"][0]) for g in GAMES}
    st = {g: window_stats(cur[g][-HOT_WINDOW:], cur[g], GAMES[g]["eras"][0]["N"], GAMES[g]["k"], GAMES[g]["eras"][0]["low_max"]) for g in GAMES}
    lc = last_check_label(history)
    body = f"""<section class="hero">
  <div class="wrap pt-6 pb-10">
    <p class="stamp"><i></i>Results verified nightly · {esc(lc)}</p>
    <h1 class="mt-3">Lotto Max &amp; Lotto 6/49 tonight: jackpots, results and number stats</h1>
    <p class="sub mt-2 max-w-3xl text-sm sm:text-base">Every draw since 1982 in one place, plus tools the official sites don't have: check your regular line against all of history, explore hot and cold numbers, and see what the odds really mean. Independent, unofficial and free.</p>
    <div class="grid gap-4 lg:grid-cols-2 mt-5">
{home_game_card("lotto_max", prep, nds["lotto_max"], st["lotto_max"])}
{home_game_card("lotto_649", prep, nds["lotto_649"], st["lotto_649"])}
    </div>
    {my_line_slot(prep)}
    <div class="mt-4">{generator_panel(st)}</div>
  </div>
</section>
{ad_slot("H1")}
<div class="wrap">
  <section aria-labelledby="recent-h">
    <p class="kicker">Recent draws</p>
    <h2 id="recent-h" class="section-title mt-1">Latest winning numbers</h2>
    <div class="grid gap-6 lg:grid-cols-2 mt-4">
      <article class="card card-max"><div class="flex items-center justify-between"><span class="badge badge-max">Lotto Max</span><a href="/lotto-max-results.html#draws" class="text-sm">Full archive →</a></div><div class="mt-3">{recent_rows("lotto_max", prep["lotto_max"])}</div></article>
      <article class="card card-649"><div class="flex items-center justify-between"><span class="badge badge-649">Lotto 6/49</span><a href="/lotto-649-results.html#draws" class="text-sm">Full archive →</a></div><div class="mt-3">{recent_rows("lotto_649", prep["lotto_649"])}</div></article>
      {max_tracker_card(prep, history, jhist, nds["lotto_max"])}
      {gold_tracker_card(prep, nds["lotto_649"])}
    </div>
  </section>
  <section class="mt-10" aria-labelledby="tools-h">
    <p class="kicker">Free tools</p>
    <h2 id="tools-h" class="section-title mt-1">Things the official sites won't do for you</h2>
    <div class="grid gap-4 md:grid-cols-3 mt-4">{tool_cards()}</div>
  </section>
</div>
{odds_band()}
{ad_slot("H2")}
<div class="wrap">
  <section aria-labelledby="guides-h">
    <p class="kicker">Guides</p>
    <h2 id="guides-h" class="section-title mt-1">How the games really work</h2>
    <p class="text-sm muted mt-1">Written by NextGen, British Columbia. Facts checked against BCLC, WCLC, OLG, CRA and Canadian Anti-Fraud Centre pages.</p>
    <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 mt-4">{guide_cards()}</div>
  </section>
</div>
{ad_slot("H3")}
<div class="wrap">
  <section class="card card-violet prose-lh" aria-labelledby="about-h">
    <h2 id="about-h">About lottohelper.ca and how this site works</h2>
    <p>lottohelper.ca is an independent, unofficial reference run from British Columbia. It keeps a complete archive of published Lotto 6/49 results since the first draw on June 12, 1982 and Lotto Max results since its launch on September 25, 2009, and explains how the games, prizes, claims and odds really work — without selling tickets or pretending to predict the next draw.</p>
    <p>A small script runs every night after midnight Pacific time. It reads the official winning numbers published by the Western Canada Lottery Corporation, checks that each draw date falls on the right weekday and that the right count of numbers is present, and only then updates this page, the two results archives and the data behind the tools. If anything fails a check, yesterday's verified data stays in place — figures are never guessed. Older draws were added in October 2026 from Loto-Québec's and WCLC's public results and cross-checked against each other. Jackpot amounts for upcoming draws are the ones WCLC advertises and can change; your provincial lottery has the final word.</p>
    <p>Hot, warm and cold labels describe the past only. Every number has exactly the same chance in every draw, which is why the generator above is labelled as entertainment and why our <a href="/hot-cold-explained.html">hot and cold guide</a> explains what the charts can and cannot tell you. Play for fun, within a budget — see <a href="/responsible-play.html">responsible play</a>.</p>
    <p>We are not affiliated with BCLC, WCLC, OLG, Loto-Québec, Atlantic Lottery or the Interprovincial Lottery Corporation. Game names belong to their owners and are used only to identify the draws. Questions or corrections: see the <a href="/contact.html">contact page</a> or read more <a href="/about.html">about the project</a>.</p>
  </section>
</div>"""
    return layout("/", "Lotto Max & Lotto 6/49 results, jackpots and stats for Canada | lottohelper.ca",
                  "Lotto Max and Lotto 6/49 results with every draw since 1982, live jackpot and Gold Ball trackers, a number checker, hot and cold stats and an odds calculator. Independent, no predictions, no ticket sales.",
                  body, active="/", scripts=("/assets/js/common.js", "/assets/js/home.js"))


# ---------------------------------------------------------------------------
# Archive pages (results + stats explorer + trackers + full history)
# ---------------------------------------------------------------------------
def since_txt(s, live):
    if s is None:
        return "not drawn yet" if live else "never drawn"
    if s == 0:
        return "in latest draw" if live else "in final draw"
    return f"{s} draw{'s' if s != 1 else ''} ago" if live else f"{s} before end"


def heatmap(win, latest_set):
    st = win["st"]
    N = st["N"]
    tiles = []
    for i in range(1, N + 1):
        h = st["heat"][i]
        latest = " latest" if (win["live"] and i in latest_set) else ""
        tiles.append(f'<div class="tile {HEAT_CLASS[h]}{latest}" title="{i}: drawn {st["counts"][i]} times in {esc(win["desc"])}; {HEAT_LABEL[h].lower()}; last seen {since_txt(st["since"][i], win["live"])}">'
                     f'<b>{i}</b><span class="c">{st["counts"][i]}×</span><span class="a">{since_txt(st["since"][i], win["live"])}</span></div>')
    cls = "heatmap-52" if N > 50 else "heatmap-50"
    legend = "".join(f'<span class="{HEAT_CLASS[j]}">{HEAT_LABEL[j]}</span>' for j in range(5))
    return (f'<div class="heatmap {cls}">{"".join(tiles)}</div>'
            f'<div class="legend mt-3">{legend}<span class="bg-white text-slate-600 ring-1 ring-slate-200">● gold dot = in the latest draw</span></div>')


def bar_list(items, top, exp=None, cls="", fmt=lambda v: f"{v}×"):
    rows = []
    for n, v in items:
        w = (v / top * 100) if top else 0
        exp_mk = f'<span class="bar-exp" style="left:{min(100, exp / top * 100):.1f}%"></span>' if exp and top else ""
        rows.append(f'<div class="bar-row {cls}">{ball(n, "xs")}<div class="bar-track"><span class="bar-fill" style="width:{w:.1f}%"></span>{exp_mk}</div><span class="bar-val">{fmt(v)}</span></div>')
    return f'<div class="bars">{"".join(rows)}</div>'


def window_panel_main(win, latest_set, default):
    st = win["st"]
    N = st["N"]
    counts = st["counts"]
    nums = range(1, N + 1)
    top = max(counts[1:]) if N else 1
    most = sorted(nums, key=lambda i: (-counts[i], i))[:10]
    least = sorted(nums, key=lambda i: (counts[i], i))[:10]
    gaps = sorted(nums, key=lambda i: (-(st["since"][i] if st["since"][i] is not None else 10 ** 6), i))[:10]
    gtop = max((st["since"][i] or 0) for i in gaps) or 1
    hidden = "" if default else " hidden"
    span = f'{short_date(st["first"])} – {short_date(st["last"])}' if st["first"] else ""
    era_note = ""
    if not win["live"]:
        era_note = (f'<p class="notice">Historical view: these draws used {esc(win["era"]["long"])}. '
                    f'They are kept separate because a different number range changes every frequency.</p>')
    expl = (f'Expected count for each number in {plural(st["draws"], "draw")}: <strong>{st["expected"]:.1f}</strong> '
            f'(typical spread ±{st["sd"]:.1f}). Colours compare each count with that expectation.')
    return f"""<div data-panel="{win['key']}"{hidden}>
  <div class="grid gap-3 sm:grid-cols-3">
    <div class="stat-tile"><p class="kicker">Window</p><p class="stat-big">{plural(st["draws"], "draw")}</p><p class="text-xs muted">{esc(span)}</p></div>
    <div class="stat-tile"><p class="kicker">🔥 Most drawn</p><p class="mt-1">{balls_row(st["hot"][:5], None, "sm")}</p></div>
    <div class="stat-tile"><p class="kicker">❄️ Least drawn</p><p class="mt-1">{balls_row(st["cold"][:5], None, "sm")}</p></div>
  </div>
  {era_note}
  <h3 class="font-display font-bold text-xl text-slate-900 mt-6">Heatmap: how often each number came up</h3>
  <p class="text-sm muted mb-3">{expl}</p>
  {heatmap(win, latest_set)}
  <div class="mt-4">{hwc_strip(st, light=True)}</div>
  <div class="grid gap-6 md:grid-cols-3 mt-6">
    <div><h3 class="font-display font-bold text-lg text-slate-900 mb-2">🔥 Drawn most often</h3>{bar_list([(n, counts[n]) for n in most], top, st["expected"], "bar-hot")}</div>
    <div><h3 class="font-display font-bold text-lg text-slate-900 mb-2">❄️ Drawn least often</h3>{bar_list([(n, counts[n]) for n in least], top, st["expected"], "bar-cold")}</div>
    <div><h3 class="font-display font-bold text-lg text-slate-900 mb-2">⏳ Longest since last seen</h3>{bar_list([(n, st["since"][n] or 0) for n in gaps], gtop, None, "bar-gap", fmt=lambda v: f"{v} dr.")}</div>
  </div>
  <p class="text-xs muted mt-2">Dashed line = expected count. "Draws since last seen" counts draws in the same number format{"" if win["live"] else " up to the end of that format"}.</p>
</div>"""


def split_rows(rows, draws, a_lbl, b_lbl):
    trs = []
    top = max([max(obs / draws if draws else 0, p) for _, _, obs, p in rows] + [0.0001])
    for a, b, obs, p in rows:
        if p < 0.002 and obs == 0:
            continue
        o = (obs / draws) if draws else 0
        trs.append(f'<tr><td>{a} {a_lbl} / {b} {b_lbl}</td><td class="tnum">{obs}</td><td class="tnum">{p * draws:.1f}</td>'
                   f'<td><span class="mini"><span class="o" style="width:{o / top * 100:.0f}%"></span><span class="e" style="width:{p / top * 100:.0f}%"></span></span></td></tr>')
    return ('<div class="table-wrap"><table><thead><tr><th>Split</th><th>Seen</th><th>Expected</th><th>Seen vs expected</th></tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')


def sum_hist(st):
    sums = st["sums"]
    if not sums:
        return ""
    N, k = st["N"], st["k"]
    dist = sum_distribution(N, k)
    lo_s, hi_s = sum(range(1, k + 1)), sum(range(N - k + 1, N + 1))
    bins = 12
    width = math.ceil((hi_s - lo_s + 1) / bins)
    obs = [0] * bins
    for s in sums:
        obs[min(bins - 1, (s - lo_s) // width)] += 1
    exp = [0.0] * bins
    for s in range(lo_s, hi_s + 1):
        exp[min(bins - 1, (s - lo_s) // width)] += dist[s] * len(sums)
    top = max(max(obs), max(exp)) or 1
    cols = "".join(f'<div title="sums {lo_s + i * width}–{min(hi_s, lo_s + (i + 1) * width - 1)}: {obs[i]} seen, {exp[i]:.1f} expected">'
                   f'<span class="hb-o" style="height:{obs[i] / top * 100:.0f}%"></span><span class="hb-e" style="bottom:{exp[i] / top * 100:.0f}%"></span></div>'
                   for i in range(bins))
    xs = "".join(f"<span>{lo_s + i * width}</span>" for i in range(bins))
    return f'<div class="hist" role="img" aria-label="Histogram of line totals compared with the expected shape">{cols}</div><div class="hist-x">{xs}</div>'


def window_panel_patterns(win, default):
    st = win["st"]
    d = st["draws"]
    hidden = "" if default else " hidden"
    pairs = "".join(f'<li>{balls_row(list(p), None, "xs")}<span class="font-bold tnum">{c}×</span></li>' for p, c in st["top_pairs"][:8])
    low_lbl = f"low (1–{st['low_max']})"
    high_lbl = f"high ({st['low_max'] + 1}–{st['N']})"
    return f"""<div data-panel="{win['key']}"{hidden}>
  <div class="grid gap-6 lg:grid-cols-2">
    <div><h3 class="font-display font-bold text-lg text-slate-900">Odd / even split</h3>{split_rows(st["odd_rows"], d, "odd", "even")}</div>
    <div><h3 class="font-display font-bold text-lg text-slate-900">High / low split</h3><p class="text-xs muted">Low = {esc(low_lbl)}, high = {esc(high_lbl)}.</p>{split_rows(st["low_rows"], d, "low", "high")}</div>
    <div><h3 class="font-display font-bold text-lg text-slate-900">Line totals (sum of the main numbers)</h3>
      <p class="text-sm muted mb-2">Lowest {st["sum_min"]}, highest {st["sum_max"]}, average {st["sum_mean"]:.1f} (long-run average {st["sum_theory"]:.1f}). Bars = draws seen, dashes = expected shape.</p>{sum_hist(st)}</div>
    <div><h3 class="font-display font-bold text-lg text-slate-900">Most common pairs</h3>
      <p class="text-sm muted mb-2">Any specific pair is expected about {st["pair_expected"]:.1f} times here. With {comb(st["N"], 2):,} possible pairs, a few always run well ahead by chance.</p>
      <ul class="rowz">{pairs}</ul>
      <p class="text-sm mt-3">Draws with at least two consecutive numbers: <strong>{st["consec_obs"]}</strong> of {d:,} ({pct(st["consec_obs"] / d if d else 0)}; long-run share {pct(st["consec_prob"])}).</p></div>
  </div>
</div>"""


def win_picker(wins, default_key):
    btns = "".join(f'<button type="button" data-win="{w["key"]}" aria-pressed="{"true" if w["key"] == default_key else "false"}">{esc(w["tab"])}</button>' for w in wins)
    return f'<div class="seg" role="group" aria-label="Choose which draws to include" data-winpick>{btns}</div>'


def draws_table(game_key, recs, gb_values=None, newest_iso=None):
    cfg = GAMES[game_key]
    head = ["Date", "Winning numbers + bonus", "Jackpot" if game_key == "lotto_max" else "Gold Ball"]
    rows = []
    month = None
    for r, gbv in zip(reversed(recs), reversed(gb_values or [None] * len(recs))):
        m = month_year(r["dt"])
        if m != month:
            month = m
            mid = r["dt"].strftime("m-%Y-%m")
            rows.append(f'<tr class="mh" id="{mid}"><th colspan="3">{esc(m)}</th></tr>')
        cls = "r newest" if r["iso"] == newest_iso else "r"
        if game_key == "lotto_max":
            last = money_short(r["jackpot"]) if r.get("jackpot") else "—"
        else:
            g = r.get("gold_ball") or {}
            if g.get("ball"):
                what = "Gold" if g["ball"] == "Gold" else "White"
                last = f'<span class="gb-ico">{gold_icon(g["ball"])} {what} · {money_short(g.get("prize"))}</span>'
            else:
                last = "—"
        empty = ' class="empty"' if last == "—" else ""
        rows.append(f'<tr class="{cls}"><td class="c-date" data-label="Date">{esc(short_date(r["dt"]))}</td>'
                    f'<td class="c-nums" data-label="Numbers">{balls_row(r["numbers"], r.get("bonus"), "sm")}</td><td data-label="{head[2]}"{empty}>{last}</td></tr>')
    th = "".join(f"<th>{h}</th>" for h in head)
    return f'<table class="draw-table"><thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def archive_about(game_key, prep, history):
    recs = prep[game_key]
    first = long_date(recs[0]["dt"])
    total = len(recs)
    if game_key == "lotto_max":
        eras = GAMES[game_key]["eras"]
        counts = {e["key"]: len(era_records(recs, e)) for e in eras}
        return f"""<h2>About Lotto Max and this archive</h2>
<p>Lotto Max is drawn every Tuesday and Friday at about 10:30 p.m. ET (7:30 p.m. PT). Since April 14, 2026, a $6 play gives you four selections of seven numbers from 1 to 52: you choose one line (or take a Quick Pick) and the terminal adds three Quick Pick lines. Seven main numbers and a bonus number are drawn. Matching all seven on one line wins or shares the main jackpot, which starts at $10 million and is capped at $90 million. Every draw also has $100,000 MaxPlus prizes, and once the jackpot passes $50 million there are $1 million MaxMillions prizes as well. The full mechanics are in our <a href="/lotto-max-maxmillions-explained.html">Lotto Max and MaxMillions guide</a>.</p>
<p>This archive holds all <strong>{total:,}</strong> Lotto Max draws since the first one on {first}. The number range has changed twice: {counts["r49"]} draws used 1–49 (2009–2019), {counts["r50"]} used 1–50 (May 2019 – April 2026) and {counts["r52"]} so far use 1–52. Because a bigger range lowers every number's share, the statistics below never mix formats: the default view is the current 1–52 format, and the older eras have their own clearly labelled tabs.</p>
<p>How it is built: draws since October 2025 come from the Western Canada Lottery Corporation's public winning-number pages and are added automatically after each draw night, once the date, weekday and count of numbers pass validation. Older draws were added in October 2026 from Loto-Québec's public results archive and cross-checked against WCLC's draw numbering. The jackpot column shows the jackpot WCLC advertised for that draw; it was only recorded from October 2026, so earlier rows show a dash. Always confirm a ticket with <a href="{GAMES[game_key]["official"]}" rel="noopener">WCLC</a> or your own provincial lottery.</p>"""
    return f"""<h2>About Lotto 6/49 and this archive</h2>
<p>Lotto 6/49 is drawn every Wednesday and Saturday at about 10:30 p.m. ET (7:30 p.m. PT). A $3 play has two parts. In the Classic Draw you pick six numbers from 1 to 49; matching all six wins or shares a fixed $5 million jackpot, and smaller prizes start at two numbers plus the bonus. Each play also carries a 10-digit Gold Ball number. One Gold Ball number is drawn every time, so somebody always wins either the guaranteed $1 million (white ball) or the Gold Ball jackpot (gold ball), which starts at $10 million and grows by $2 million after every white ball. Our <a href="/lotto-649-gold-ball-explained.html">Gold Ball guide</a> explains the drum and the odds.</p>
<p>This archive holds all <strong>{total:,}</strong> Lotto 6/49 draws since the very first one on {first}. The main numbers have always been drawn from 1 to 49, so statistics can use the whole history; the window picker lets you compare the last 10, 50 or 100 draws with the full record.</p>
<p>How it is built: draws since October 2025 come from the Western Canada Lottery Corporation's public winning-number pages and are added automatically after each draw night, once the date, weekday and numbers pass validation. Older draws were added in October 2026 from Loto-Québec's public results archive and cross-checked against WCLC. Gold Ball results are shown where they were published with the draw (August 2026 onward). Confirm any ticket with <a href="{GAMES[game_key]["official"]}" rel="noopener">WCLC</a> or your provincial lottery.</p>"""


def render_archive(game_key, history, prep, today, jhist):
    cfg = GAMES[game_key]
    recs = prep[game_key]
    name = cfg["name"]
    latest = recs[-1]
    nd = next_draw_info(game_key, history, today)
    wins = stat_windows(game_key, recs)
    default_key = DEFAULT_WINDOW
    latest_set = set(latest["numbers"])

    stale = ""
    exp = expected_latest_draw(today, cfg["draw_weekdays"])
    if latest["dt"].date() < exp:
        stale = (f'<p class="notice">The {long_date(datetime.combine(exp, datetime.min.time()))} draw is not shown yet. '
                 f'Results are added after automatic checks; see <a href="{cfg["official"]}" rel="noopener">WCLC</a> in the meantime.</p>')

    panels_main = "".join(window_panel_main(w, latest_set, w["key"] == default_key) for w in wins)
    panels_pat = "".join(window_panel_patterns(w, w["key"] == default_key) for w in wins)

    if game_key == "lotto_max":
        tracker = max_tracker_card(prep, history, jhist, nd)
        gbv = None
    else:
        tracker = gold_tracker_card(prep, nd)
        gbv = gold_ball_derivation(recs)

    year_now = latest["dt"].year
    cutoff = (latest["dt"] - timedelta(days=183)).strftime("%Y-%m-%d")
    recent = [r for r in recs if r["iso"] > cutoff]
    recent_gb = None
    if gbv is not None:
        recent_gb = [v for r, v in zip(recs, gbv) if r["iso"] > cutoff]
    years = sorted({r["dt"].year for r in recs}, reverse=True)
    year_btns = "".join(f'<button type="button" data-year="{y}" aria-pressed="false">{y}</button>' for y in years)
    months = []
    seen = set()
    for r in reversed(recent):
        k = r["dt"].strftime("%Y-%m")
        if k not in seen:
            seen.add(k)
            months.append((k, r["dt"].strftime("%b %Y")))
    jump_months = "".join(f'<a class="m" href="#m-{k}">{esc(lbl)}</a>' for k, lbl in months[:6])

    hero = f"""<section class="hero {cfg['hero']}">
  <div class="wrap pt-6 pb-8">
    <div class="flex flex-wrap items-center gap-2"><span class="badge {cfg['badge']}">{name}</span><span class="stamp"><i></i>{esc(last_check_label(history))}</span></div>
    <h1 class="mt-3">{name} results, number stats and full draw history</h1>
    <p class="sub mt-2 max-w-3xl">Latest numbers, jackpot tracker and an interactive stats explorer covering all {len(recs):,} draws since {recs[0]["dt"].year}.</p>
    <div class="grid gap-4 lg:grid-cols-5 mt-5">
      <div class="glass gcard {cfg['gcard']} lg:col-span-3">{latest_block(game_key, latest)}{stale}
        <div class="flex flex-wrap gap-3 mt-5"><a class="btn-gold" href="/check-my-numbers.html">🎯 Check my numbers</a><a class="btn-ghost" href="#stats">📊 Stats explorer</a></div></div>
      <div class="glass gcard {cfg['gcard']} lg:col-span-2">{next_draw_block(game_key, nd)}</div>
    </div>
  </div>
</section>"""

    hot_msg = ("Every number has the same chance in every draw. These charts describe what already happened; "
               'they do not change the odds of the next draw. <a href="/hot-cold-explained.html">Why hot and cold numbers do not predict anything</a>.')

    body = f"""{hero}
<div class="wrap mt-4">
  <nav class="jump" aria-label="On this page"><a href="#about">About</a><a href="#stats">📊 Stats</a><a href="#tracker">{"💰 Jackpot" if game_key == "lotto_max" else "🟡 Gold Ball"}</a><a href="#patterns">Patterns</a><a href="#draws">All draws</a><a href="#years">By year</a>{jump_months}</nav>
  <section id="about" class="card card-violet prose-lh mt-4">{archive_about(game_key, prep, history)}</section>
</div>
{ad_slot("A1")}
<div class="wrap">
  <section id="stats" class="card {cfg['card']}" style="scroll-margin-top:70px">
    <p class="kicker">Stats explorer</p>
    <h2 class="section-title mt-1">{name} number frequency, hot &amp; cold</h2>
    <p class="mt-2 text-sm">{hot_msg}</p>
    <div class="mt-4">{win_picker(wins, default_key)}</div>
    <div class="mt-5">{panels_main}</div>
  </section>
  <section id="tracker" class="mt-8" style="scroll-margin-top:70px">{tracker}</section>
  <section id="patterns" class="card {cfg['card']} mt-8" style="scroll-margin-top:70px">
    <p class="kicker">Patterns</p>
    <h2 class="section-title mt-1">Odd/even, high/low, totals and pairs</h2>
    <p class="mt-2 text-sm muted">Same window as the stats explorer above. Long-run shares are exact probabilities for {cfg["k"]} numbers drawn at random.</p>
    <div class="mt-3">{win_picker(wins, default_key)}</div>
    <div class="mt-5">{panels_pat}</div>
  </section>
</div>
{ad_slot("A2")}
<div class="wrap">
  <section id="draws" class="card {cfg['card']}" style="scroll-margin-top:70px">
    <p class="kicker">All draws</p>
    <h2 class="section-title mt-1">{name} winning numbers: the last 6 months</h2>
    <p class="text-sm muted mt-1">{len(recent)} draws, newest first. Every older draw is one tap away in the year browser below.</p>
    <div class="mt-4">{draws_table(game_key, recent, recent_gb, latest["iso"])}</div>
  </section>
  <section id="years" class="card {cfg['card']} mt-8" style="scroll-margin-top:70px" data-archive="{cfg['slug']}">
    <p class="kicker">Browse by year</p>
    <h2 class="section-title mt-1">Every {name} draw since {recs[0]["dt"].year}</h2>
    <p class="text-sm muted mt-1">Pick a year to load its draws from our data file (about {"15" if game_key == "lotto_max" else "45"} KB compressed, loaded only when you ask).</p>
    <div class="seg mt-4" role="group" aria-label="Year">{year_btns}</div>
    <div class="mt-4" data-year-out aria-live="polite"></div>
  </section>
</div>
{ad_slot("A3")}
<div class="wrap">
  <section class="card card-violet prose-lh">
    <h2>What this page cannot tell you</h2>
    <p>It cannot tell you which numbers will come up next. Lotto draws use certified random equipment, and each draw is independent of every draw before it. A number that has not appeared for {max((w["st"]["since"][i] or 0) for w in wins[:1] for i in range(1, w["st"]["N"] + 1))} draws has exactly the same chance as the number drawn last night. Over thousands of draws, the counts drift toward the expected value, but in any short window some numbers will always look hot and others cold.</p>
    <p>It also cannot tell you whether a ticket won. Prize amounts depend on how many people matched, and official records are the only basis for a claim. Use your ticket checker or <a href="{cfg["official"]}" rel="noopener">WCLC's winning numbers</a> to confirm, and see our guide on <a href="/how-to-claim-lottery-prize-bc.html">claiming a prize in BC and Western Canada</a>.</p>
    <p>What it can do: show you the complete record honestly, let you <a href="/check-my-numbers.html">check your own line against all {len(recs):,} draws</a>, and put the odds in context with the <a href="/lotto-odds-calculator.html">odds calculator</a>. Sources: WCLC (draws since October 2025 and all jackpot and Gold Ball data) and Loto-Québec (earlier draws).</p>
  </section>
</div>"""
    title = f"{name} results, stats & every draw since {recs[0]['dt'].year}"
    desc = (f"Latest {name} winning numbers, jackpot tracker, hot and cold number stats with a window picker, "
            f"and all {len(recs):,} draws since {recs[0]['dt'].year}. Independent and unofficial.")
    return layout(cfg["path"], title, desc, body, scripts=("/assets/js/common.js", "/assets/js/archive.js"))


# ---------------------------------------------------------------------------
# Check my numbers
# ---------------------------------------------------------------------------
def render_checker(prep):
    nmax = len(prep["lotto_max"])
    n649 = len(prep["lotto_649"])
    cur = len(era_records(prep["lotto_max"], GAMES["lotto_max"]["eras"][0]))
    picks = "".join(f'<button type="button" class="pick" data-n="{i}" aria-pressed="false">{i}</button>' for i in range(1, 53))
    body = f"""<section class="hero hero-tool">
  <div class="wrap pt-6 pb-8">
    <p class="stamp"><i></i>{nmax:,} Lotto Max + {n649:,} Lotto 6/49 draws</p>
    <h1 class="mt-3">🎯 Check my numbers against every draw</h1>
    <p class="sub mt-2 max-w-3xl">Enter the line you always play and see every time it would have matched 3 or more numbers — back to 1982 for Lotto 6/49 and 2009 for Lotto Max — plus your best result ever and a count for each prize tier.</p>
  </div>
</section>
<div class="wrap mt-6">
  <section class="card card-violet" id="checker" data-max-cur="{cur}">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="seg" role="group" aria-label="Game"><button type="button" data-game="max" aria-pressed="true">Lotto Max (7 numbers)</button><button type="button" data-game="649" aria-pressed="false">Lotto 6/49 (6 numbers)</button></div>
      <p class="text-sm muted" data-count-label>Pick 7 numbers from 1 to 52.</p>
    </div>
    <div class="pick-grid mt-4" data-picks>{picks}</div>
    <div class="grid gap-3 md:grid-cols-4 mt-4 items-end">
      <label class="field md:col-span-2">Or type your numbers<input type="text" inputmode="numeric" autocomplete="off" data-typed placeholder="e.g. 3 11 19 24 33 40 47"></label>
      <label class="field">Draws to search<select data-scope><option value="all">All draws since 2009</option><option value="cur">Current 1–52 format only</option></select></label>
      <label class="field">Show matches of<select data-min><option value="3">3 or more</option><option value="4">4 or more</option><option value="5">5 or more</option></select></label>
    </div>
    <div class="flex flex-wrap items-center gap-3 mt-4">
      <button type="button" class="btn" data-run disabled>Check my line</button>
      <button type="button" class="btn-light" data-clear>Clear</button>
      <label class="check"><input type="checkbox" data-save> Save this line in this browser (shows on the home page)</label>
    </div>
    <p class="text-xs muted mt-2" data-msg aria-live="polite"></p>
  </section>
  <section class="card mt-6" id="results" aria-live="polite" hidden>
    <div data-summary></div>
    <div class="grid gap-6 lg:grid-cols-2 mt-4"><div data-tiers></div><div data-best></div></div>
    <h2 class="section-title mt-6">Every draw your line matched</h2>
    <div class="mt-3" data-list></div>
  </section>
  <section class="card card-violet prose-lh mt-8">
    <h2>How the number checker works</h2>
    <p>The checker compares your line with the winning numbers of every draw in our archive: {n649:,} Lotto 6/49 draws since June 12, 1982 and {nmax:,} Lotto Max draws since September 25, 2009. It runs entirely in your browser. When you press the button it downloads our compact results file for that game (the same data shown on the results pages) and counts how many of your numbers match the main numbers of each draw, then whether the bonus number is also on your line.</p>
    <p>Results are grouped by prize tier using the names on the current prize tables — for Lotto Max, 7 of 7 down to 3 of 7, with the "+ bonus" tiers; for Lotto 6/49, 6 of 6 down to 2 of 6 + bonus. We deliberately do not show dollar amounts. Most tiers are a share of a prize pool, so what a 5 of 6 paid in 1995 is not what it pays today, and older draws used different prize structures. Treat the tier counts as a fun "what if" rather than a ledger.</p>
    <h3>Why Lotto Max has a format choice</h3>
    <p>Lotto Max numbers were drawn from 1 to 49 until May 2019, from 1 to 50 until April 10, 2026, and from 1 to 52 since April 14, 2026. A line with 51 or 52 could never have matched those numbers before 2026, and the chance of each match changes with the range. "Current format only" searches the {cur} draws in the 1–52 format; "All draws" searches all {nmax:,}.</p>
    <h3>What the results mean</h3>
    <p>If your line has matched 4 numbers a few times since 2009, that is about what chance alone produces: the odds of 4 of 7 on one line are roughly 1 in 72 per draw in today's format. A line that has never matched 5 is not "due"; every draw is a fresh draw. You can compare your counts with what to expect in the <a href="/lotto-odds-calculator.html">odds calculator</a>, and read why streaks appear in <a href="/hot-cold-explained.html">our hot and cold guide</a>.</p>
    <h3>Privacy</h3>
    <p>Your numbers never leave your device. If you tick "Save this line", it is stored in your browser's local storage so the home page can show how it did in the latest draw; untick it or press Clear to remove it. See the <a href="/privacy.html">privacy policy</a>.</p>
    <p class="text-sm">Always confirm a real ticket with your provincial lottery's ticket checker. This tool is for curiosity and fun only.</p>
  </section>
</div>"""
    return layout("/check-my-numbers.html", "Check my numbers: Lotto Max & 6/49 history checker",
                  "Enter your regular Lotto Max or Lotto 6/49 line and see every past draw it matched 3+, 4+ or 5+ numbers, your best result ever and a count per prize tier.",
                  body, scripts=("/assets/js/common.js", "/assets/js/checker.js"))


# ---------------------------------------------------------------------------
# Odds calculator
# ---------------------------------------------------------------------------
def yearly_pct(p):
    if p > 0.999:
        return "over 99.9%"
    return pct(p) if p >= 0.001 else "{:.4f}%".format(p * 100)


def odds_rows(game_key, plays):
    rows = []
    for name, prize, o in ODDS[game_key]["tiers"]:
        p = 1 / o
        yr = 1 - (1 - p) ** plays
        rows.append(f'<tr><td class="font-bold">{name}</td><td>{esc(prize)}</td><td class="tnum">1 in {fmt_odds(o)}</td><td class="tnum">{yearly_pct(yr)}</td></tr>')
    return "".join(rows)


def render_odds_calc():
    plays = 104
    odds_js = json.dumps({g: {"per": v["per"], "any": v["any"], "price": GAMES[g]["price"], "tiers": [[t[0], t[1], t[2]] for t in v["tiers"]]} for g, v in ODDS.items()}, separators=(",", ":"))
    p = 1 / ODDS["lotto_max"]["tiers"][0][2]
    yrs = 1 / (p * plays)
    flips = math.log2(ODDS["lotto_max"]["tiers"][0][2])
    body = f"""<section class="hero hero-tool">
  <div class="wrap pt-6 pb-8">
    <p class="stamp"><i></i>Official odds per play · Lotto Max 2026 format</p>
    <h1 class="mt-3">🧮 Lotto odds calculator</h1>
    <p class="sub mt-2 max-w-3xl">Tell it how you play and it shows your real chances for every prize tier over a year, what that year costs, and comparisons that make 1 in 33 million feel like a real number.</p>
  </div>
</section>
<div class="wrap mt-6">
  <section class="card card-violet" id="calc" data-odds='{esc(odds_js)}'>
    <div class="grid gap-4 md:grid-cols-4 items-end">
      <label class="field">Game<select data-in="game"><option value="lotto_max">Lotto Max ($6 per play)</option><option value="lotto_649">Lotto 6/49 ($3 per play)</option></select></label>
      <label class="field">Plays per draw<input type="number" min="1" max="100" value="1" data-in="plays"></label>
      <label class="field">Draws per week<select data-in="dpw"><option value="2">Both draws (2)</option><option value="1">One draw</option></select></label>
      <label class="field">Weeks per year<input type="number" min="1" max="52" value="52" data-in="weeks"></label>
    </div>
    <div class="grid gap-3 sm:grid-cols-3 mt-6">
      <div class="stat-tile"><p class="kicker">Plays per year</p><p class="stat-big" data-out="n">{plays}</p></div>
      <div class="stat-tile"><p class="kicker">Cost per year</p><p class="stat-big" data-out="cost">${plays * 6:,}</p></div>
      <div class="stat-tile"><p class="kicker">Chance of the jackpot this year</p><p class="stat-big" data-out="jp">1 in {1 / (1 - (1 - p) ** plays):,.0f}</p></div>
    </div>
    <div class="table-wrap mt-6"><table><thead><tr><th>Prize tier</th><th>Prize</th><th>Odds per play</th><th>Chance in a year</th></tr></thead><tbody data-out="rows">{odds_rows("lotto_max", plays)}</tbody></table></div>
    <ul class="mt-4 space-y-2 text-slate-700" data-out="compare">
      <li>🗓️ At this rate you would expect to wait about <strong>{yrs:,.0f} years</strong> for one jackpot win on average.</li>
      <li>🪙 One play hitting the jackpot is about as likely as calling <strong>{flips:.0f} coin flips</strong> in a row correctly.</li>
      <li>💵 Over a year you spend <strong>${plays * 6:,}</strong>; any prize at all comes about once every {ODDS["lotto_max"]["any"]} plays, and most of those are a Free Play.</li>
    </ul>
  </section>
  <section class="card card-violet prose-lh mt-8">
    <h2>How these odds are worked out</h2>
    <p>Lottery odds come from counting. In Lotto 6/49 there are 13,983,816 different ways to choose 6 numbers from 49, and only one of them matches the draw, so a single line has a 1 in 13,983,816 chance at the Classic jackpot. In today's Lotto Max there are 133,784,560 ways to choose 7 numbers from 52; a $6 play gives you four selections, which is why the official odds of the jackpot are 1 in 33,446,140 per play. Lower tiers have many more winning combinations, so their odds are far shorter. The figures in the table are the official odds per play published with the prize tables by the Western Canada Lottery Corporation.</p>
    <p>The yearly numbers use simple probability. If one play has a chance <em>p</em> of winning a tier, then <em>n</em> independent plays have a chance of 1 − (1 − <em>p</em>)<sup>n</sup> of winning it at least once. For rare prizes that is almost exactly <em>n</em> × <em>p</em>: doubling your spend doubles your chance, but double a tiny number is still tiny. Buying 104 Lotto Max plays a year — one at every draw — gives about a 1 in 322,000 chance of a jackpot that year.</p>
    <h3>What the calculator leaves out</h3>
    <p>It shows chances, not expected winnings. Most Lotto Max and Lotto 6/49 prizes are shares of a pool, so the amount depends on ticket sales and on how many people match. It also ignores MaxMillions, MaxPlus, Gold Ball and Extra or Encore add-ons, which have their own rules; see our <a href="/lotto-max-maxmillions-explained.html">Lotto Max guide</a>, <a href="/lotto-649-gold-ball-explained.html">Gold Ball guide</a> and <a href="/extra-and-encore-explained.html">Extra and Encore guide</a>. And no pattern, frequency chart or "system" changes any number in the table. Every combination, including 1-2-3-4-5-6, has exactly the same chance. Choosing unusual numbers only changes how many people you might share a jackpot with.</p>
    <p>If the cost-per-year line makes you wince, that is useful information. Set a budget you would happily spend on any other entertainment, and see our <a href="/responsible-play.html">responsible play page</a> for free, confidential help lines in every province. The full derivation of the jackpot odds is in our <a href="/odds.html">odds guide</a>.</p>
  </section>
</div>"""
    return layout("/lotto-odds-calculator.html", "Lotto odds calculator: Lotto Max & 6/49 chances per year",
                  "Work out your real chances of every Lotto Max and Lotto 6/49 prize tier over a year of play, what that year costs, and plain-English comparisons.",
                  body, scripts=("/assets/js/odds.js",))


# ---------------------------------------------------------------------------
# Compact data for the client-side tools
# ---------------------------------------------------------------------------
def data_json(game_key, prep):
    cfg = GAMES[game_key]
    draws = []
    for r in prep[game_key]:
        row = [r["iso"], sorted(r["numbers"]), r.get("bonus") or 0]
        if game_key == "lotto_649" and (r.get("gold_ball") or {}).get("ball"):
            row.append(r["gold_ball"]["ball"][0])
        draws.append(row)
    return json.dumps({
        "game": game_key, "name": cfg["name"], "k": cfg["k"],
        "eras": [{"N": e["N"], "start": e["start"], "end": e["end"], "label": e["label"]} for e in cfg["eras"]],
        "sources": "WCLC (wclc.com) and Loto-Québec (lotoquebec.com) published results; compiled by lottohelper.ca",
        "draws": draws,
    }, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def page_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_site(history, today):
    prep = {g: prep_records(history.get(g) or []) for g in GAMES}
    jhist = update_jackpot_history(history, prep)
    pages = {}
    pages["/"] = ("index.html", render_index(history, prep, today, jhist))
    for key, cfg in GAMES.items():
        pages[cfg["path"]] = (cfg["path"].lstrip("/"), render_archive(key, history, prep, today, jhist))
    pages["/check-my-numbers.html"] = ("check-my-numbers.html", render_checker(prep))
    pages["/lotto-odds-calculator.html"] = ("lotto-odds-calculator.html", render_odds_calc())
    pages["/guides.html"] = ("guides.html", render_guides_index())
    for slug, meta, body in load_content_pages():
        pages[f"/{slug}.html"] = (f"{slug}.html", render_content_page(slug, meta, body))

    for path, (fname, text) in pages.items():
        write_file(fname, text)
    write_file("404.html", render_404())
    for key, cfg in GAMES.items():
        write_file(os.path.join(DATA_DIR, cfg["slug"] + ".json"), data_json(key, prep))

    lastmod = {}
    if os.path.exists(LASTMOD_FILE):
        try:
            with open(LASTMOD_FILE, encoding="utf-8") as f:
                lastmod = json.load(f)
        except Exception:
            lastmod = {}
    today_s = today.strftime("%Y-%m-%d")
    new_lastmod = {}
    for path, (fname, text) in pages.items():
        h = page_hash(text)
        old = lastmod.get(path) or {}
        new_lastmod[path] = {"sha256": h, "date": old.get("date") if old.get("sha256") == h and old.get("date") else today_s}
    with open(LASTMOD_FILE, "w", encoding="utf-8") as f:
        json.dump(new_lastmod, f, indent=2, sort_keys=True)
        f.write("\n")

    entries = "\n".join(
        f"  <url><loc>{SITE}{path}</loc><lastmod>{new_lastmod[path]['date']}</lastmod></url>"
        for path in sorted(pages, key=lambda p: (p != "/", p))
    )
    write_file("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + entries + "\n</urlset>\n")
    print(f"[INFO] Built {len(pages)} pages + 404.html + data/*.json; sitemap.xml has {len(pages)} URLs.")
