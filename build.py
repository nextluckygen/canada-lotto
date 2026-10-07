"""Static site builder for lottohelper.ca.

Renders every public page from:
  * content/*.html        hand-written pages and guides (body fragments + a JSON meta header)
  * draw_history.json     verified draw results collected by main.py

Outputs (repo root, served as-is by Vercel):
  index.html, lotto-max-results.html, lotto-649-results.html, guides.html, 404.html,
  one .html per content/ file, sitemap.xml, lastmod.json (bookkeeping for real <lastmod> dates)

Nothing here fetches from the network, so `python main.py --build-only` is safe to run anywhere.
"""
import hashlib
import html
import json
import math
import os
import re
from datetime import datetime, timedelta

SITE = "https://lottohelper.ca"
SITE_NAME = "lottohelper.ca"
ADSENSE_TAG = (
    '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
    '?client=ca-pub-5048509015899303" crossorigin="anonymous"></script>'
)
CSS_HREF = "/assets/site.css"
CONTENT_DIR = "content"
LASTMOD_FILE = "lastmod.json"
GOLD_BALL_START = 10_000_000
GOLD_BALL_STEP = 2_000_000
GOLD_BALL_BALLS = 30

# Guides, in the order they appear on the guides index, homepage and footer.
GUIDES = [
    ("lotto-max-maxmillions-explained", "How Lotto Max, MaxPlus and MaxMillions work",
     "The 2026 Lotto Max format: four selections from 1–52, $100,000 MaxPlus prizes and $1 million MaxMillions draws."),
    ("lotto-649-gold-ball-explained", "How the Lotto 6/49 Gold Ball draw works",
     "The fixed $5 million Classic jackpot, the 30-ball Gold Ball drum, and why someone wins every draw."),
    ("how-to-claim-lottery-prize-bc", "How to check and claim a lottery prize in BC and Western Canada",
     "Ticket checkers, signing your ticket, ID, claim limits for BCLC and WCLC, and the one-year deadline."),
    ("are-lottery-winnings-taxed-canada", "Are lottery winnings taxed in Canada?",
     "What the CRA says about prizes, the interest you earn afterwards, and common misunderstandings."),
    ("extra-and-encore-explained", "Extra and Encore explained",
     "The $1 add-on games: BC Extra, WCLC Extra and Ontario's Encore are different games with different odds."),
    ("lottery-scams-canada", "Common lottery scams in Canada and how to spot them",
     "Advance-fee 'you won' messages, fake cheques, ticket-photo requests and number-selling schemes."),
    ("odds", "Lotto 6/49 and Lotto Max odds explained",
     "Where 1 in 13,983,816 and 1 in 33,446,140 come from, and what no system can change."),
    ("hot-cold-explained", "Why hot and cold numbers do not predict the next draw",
     "What a frequency table measures, and why short samples always look streaky."),
    ("how-canada-lotto-works", "Who runs Lotto 6/49 and Lotto Max in Canada",
     "The Interprovincial Lottery Corporation, provincial operators and where this site fits."),
]

NAV = [
    ("/", "Home"),
    ("/lotto-max-results.html", "Lotto Max results"),
    ("/lotto-649-results.html", "Lotto 6/49 results"),
    ("/guides.html", "Guides"),
    ("/responsible-play.html", "Responsible play"),
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
        "name": "Lotto Max",
        "path": "/lotto-max-results.html",
        "N": 52,
        "k": 7,
        "low_max": 26,
        "draw_weekdays": (1, 4),
        "draw_days": "Tuesday and Friday",
        "official": "https://www.wclc.com/winning-numbers/lotto-max-extra.htm",
        "guide": "/lotto-max-maxmillions-explained.html",
        "ball_class": "ball ball-max",
    },
    "lotto_649": {
        "name": "Lotto 6/49",
        "path": "/lotto-649-results.html",
        "N": 49,
        "k": 6,
        "low_max": 24,
        "draw_weekdays": (2, 5),
        "draw_days": "Wednesday and Saturday",
        "official": "https://www.wclc.com/winning-numbers/lotto-649-extra.htm",
        "guide": "/lotto-649-gold-ball-explained.html",
        "ball_class": "ball ball-649",
    },
}

esc = html.escape


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_date(s):
    return datetime.strptime(s, "%A, %B %d, %Y")


def long_date(dt):
    return f"{dt.strftime('%A, %B')} {dt.day}, {dt.year}"


def short_date(dt):
    return f"{dt.strftime('%a, %b')} {dt.day}, {dt.year}"


def money(n):
    if n is None:
        return "—"
    if n >= 1_000_000 and n % 1_000_000 == 0:
        return f"${n // 1_000_000} million"
    return f"${n:,}"


def comb(n, k):
    return math.comb(n, k)


def balls_html(numbers, bonus, ball_class, small=False):
    size = " ball-sm" if small else ""
    parts = [f'<span class="{ball_class}{size}">{n}</span>' for n in numbers]
    if bonus is not None:
        parts.append(f'<span class="ball ball-bonus{size}" title="Bonus number">{bonus}</span>')
    label = ", ".join(str(n) for n in numbers) + (f", bonus {bonus}" if bonus is not None else "")
    return f'<span class="balls" aria-label="{esc(label)}">{"".join(parts)}</span>'


def write_file(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
def nav_html(active):
    items = []
    for href, label in NAV:
        cls = "nav-link nav-active" if href == active else "nav-link"
        items.append(f'<a href="{href}" class="{cls}">{esc(label)}</a>')
    return "\n".join(items)


def footer_html():
    legal = " · ".join(f'<a href="{h}">{esc(t)}</a>' for h, t in FOOTER_LEGAL)
    guides = "".join(f'<li><a href="/{slug}.html">{esc(title)}</a></li>' for slug, title, _ in GUIDES)
    return f"""<footer class="site-footer">
  <div class="mx-auto max-w-5xl px-4 py-10 grid gap-8 md:grid-cols-3">
    <div class="space-y-2">
      <p class="font-bold text-white">lottohelper.ca</p>
      <p>An independent, unofficial reference for Lotto Max and Lotto 6/49 results and plain-language guides. Run by NextGen from British Columbia, Canada.</p>
      <p>Not affiliated with BCLC, WCLC, OLG, Loto-Québec, Atlantic Lottery or the Interprovincial Lottery Corporation. We do not sell tickets or predict draws. 19+ in most provinces (18+ in Alberta, Manitoba and Quebec).</p>
    </div>
    <div>
      <p class="font-bold text-white mb-2">Results &amp; guides</p>
      <ul class="space-y-1">
        <li><a href="/lotto-max-results.html">Lotto Max results archive</a></li>
        <li><a href="/lotto-649-results.html">Lotto 6/49 results archive</a></li>
        <li><a href="/guides.html">All guides</a></li>
        {guides}
      </ul>
    </div>
    <div>
      <p class="font-bold text-white mb-2">Site information</p>
      <p class="leading-7">{legal}</p>
      <p class="mt-4">Official results and prize claims: your provincial lottery corporation. If anything here disagrees with an official source, the official source is correct.</p>
      <p class="mt-4">© 2026 lottohelper.ca</p>
    </div>
  </div>
</footer>"""


def layout(path, title, description, body, active=None, noindex=False):
    full_title = f"{title} | {SITE_NAME}" if path != "/" else title
    canonical = SITE + path
    robots = '<meta name="robots" content="noindex">\n  ' if noindex else ""
    canonical_tag = "" if noindex else f'<link rel="canonical" href="{canonical}">\n  '
    return f"""<!DOCTYPE html>
<html lang="en-CA">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(full_title)}</title>
  <meta name="description" content="{esc(description)}">
  {robots}{canonical_tag}<meta property="og:type" content="website">
  <meta property="og:site_name" content="{SITE_NAME}">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:url" content="{canonical}">
  <link rel="stylesheet" href="{CSS_HREF}">
  {ADSENSE_TAG}
</head>
<body class="bg-slate-50 text-slate-800 antialiased">
  <a href="#main" class="sr-only focus:not-sr-only">Skip to content</a>
  <div class="bg-slate-900 text-amber-100 text-xs text-center py-2 px-3">
    19+ · Unofficial independent site · Not BCLC, WCLC, OLG, Loto-Québec or ILC · We do not sell tickets ·
    <a href="/responsible-play.html" class="underline font-semibold text-white">Play responsibly</a>
  </div>
  <header class="site-header">
    <div class="mx-auto max-w-5xl px-4 py-4 flex flex-wrap items-center justify-between gap-3">
      <a href="/" class="flex items-center gap-3 no-underline">
        <span class="logo-badge">LOTTOHELPER.CA</span>
        <span class="hidden sm:block text-sm text-teal-50">Canadian lotto results &amp; plain-language guides</span>
      </a>
      <nav class="flex flex-wrap gap-1 text-sm" aria-label="Main">
{nav_html(active or path)}
      </nav>
    </div>
  </header>
  <main id="main" class="mx-auto max-w-5xl px-4 py-8">
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
    return (f'<p class="byline">Written by NextGen, British Columbia · Last updated {esc(updated)}</p>')


def related_guides(slug):
    items = [(s, t) for s, t, _ in GUIDES if s != slug][:5]
    lis = "".join(f'<li><a href="/{s}.html">{esc(t)}</a></li>' for s, t in items)
    return (f'<aside class="card mt-8"><h2 class="text-lg font-bold text-slate-900 mb-2">More guides</h2>'
            f'<ul class="list-disc pl-5 space-y-1 text-teal-800">{lis}</ul>'
            f'<p class="mt-3 text-sm"><a href="/guides.html">See all guides →</a></p></aside>')


def render_content_page(slug, meta, body):
    if meta.get("kind") == "guide":
        body = body.replace("</h1>", "</h1>\n" + guide_byline(meta), 1)
        inner = f'<article class="card prose-lh">{body}</article>{related_guides(slug)}'
    else:
        inner = f'<article class="card prose-lh">{body}</article>'
    path = f"/{slug}.html"
    return layout(path, meta["title"], meta["description"], inner, active=meta.get("nav", path))


def render_guides_index():
    cards = "".join(
        f'<a href="/{s}.html" class="guide-card"><h2 class="font-bold text-slate-900">{esc(t)}</h2>'
        f'<p class="text-sm text-slate-600 mt-1">{esc(d)}</p></a>'
        for s, t, d in GUIDES
    )
    body = f"""<section class="card prose-lh">
<h1>Guides</h1>
<p class="byline">Written by NextGen, British Columbia · Last updated October 2026</p>
<p>These guides explain how Canada's national lotto games actually work: what you are buying, how prizes are paid, how to claim, what is taxed, and how to avoid the scams that circulate after every big jackpot. They are written for players in British Columbia and Western Canada first, with notes where Ontario, Quebec or Atlantic Canada differ.</p>
<p>Every factual claim is checked against the operator or government page linked inside each guide (BCLC, WCLC, OLG, the Canada Revenue Agency or the Canadian Anti-Fraud Centre). Game rules change — Lotto Max changed format in April 2026 — so when a guide and an official page disagree, follow the official page and <a href="/contact.html">tell us</a> so we can fix it.</p>
<p>None of these guides will tell you which numbers to pick. No guide can: every draw is independent, and the odds on a ticket are fixed by the game design.</p>
</section>
<section class="grid gap-4 sm:grid-cols-2 mt-6">{cards}</section>"""
    return layout("/guides.html", "Lotto guides for Canadian players",
                  "Plain-language guides to Lotto Max, Lotto 6/49, Gold Ball, MaxMillions, Extra, Encore, prize claims in BC, taxes and lottery scams in Canada.",
                  body, active="/guides.html")


def render_404():
    body = """<section class="card prose-lh text-center">
<h1>Page not found</h1>
<p>The page you asked for is not here. Older per-draw pages were merged into two results archives in October 2026, so a bookmarked link may have moved.</p>
<p><a href="/lotto-max-results.html">Lotto Max results archive</a> · <a href="/lotto-649-results.html">Lotto 6/49 results archive</a> · <a href="/guides.html">Guides</a> · <a href="/">Home</a></p>
<p>If you followed a broken link on this site, please let us know through the <a href="/contact.html">contact page</a>.</p>
</section>"""
    return layout("/404.html", "Page not found", "This page could not be found on lottohelper.ca.", body,
                  active="", noindex=True)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def gold_ball_derivation(records):
    """Return a list (same order as records) of Gold Ball jackpot amounts for each draw,
    derived only from published data and WCLC's published rule (starts at $10M after a
    Gold Ball win and grows $2M after every white ball). None where it cannot be known."""
    n = len(records)
    jp = [None] * n
    for i, r in enumerate(records):
        gb = r.get("gold_ball") or {}
        if r.get("gold_ball_jackpot"):
            jp[i] = r["gold_ball_jackpot"]
        if gb.get("ball") == "Gold" and gb.get("prize"):
            jp[i] = gb["prize"]
    # forward pass
    for i in range(1, n):
        if jp[i] is not None:
            continue
        prev = records[i - 1].get("gold_ball") or {}
        if prev.get("ball") == "Gold":
            jp[i] = GOLD_BALL_START
        elif prev.get("ball") == "White" and jp[i - 1] is not None:
            jp[i] = jp[i - 1] + GOLD_BALL_STEP
    # backward pass (a white-ball draw was worth $2M less than the next draw)
    for i in range(n - 2, -1, -1):
        if jp[i] is not None:
            continue
        gb = records[i].get("gold_ball") or {}
        if gb.get("ball") == "White" and jp[i + 1] is not None and jp[i + 1] > GOLD_BALL_START:
            jp[i] = jp[i + 1] - GOLD_BALL_STEP
    return jp


def game_stats(records, cfg):
    N, k = cfg["N"], cfg["k"]
    draws = len(records)
    counts = {i: 0 for i in range(1, N + 1)}
    last_seen = {i: None for i in range(1, N + 1)}
    bonus_counts = {i: 0 for i in range(1, N + 1)}
    for idx, r in enumerate(records):
        for x in r["numbers"]:
            counts[x] += 1
            last_seen[x] = idx
        if r.get("bonus") in bonus_counts:
            bonus_counts[r["bonus"]] += 1
    p = k / N
    expected = draws * p
    sd = math.sqrt(draws * p * (1 - p)) if draws else 0
    lo, hi = expected - 2 * sd, expected + 2 * sd
    outside = [i for i in counts if counts[i] < lo or counts[i] > hi]
    since = {i: (draws - 1 - last_seen[i]) if last_seen[i] is not None else None for i in counts}

    total_C = comb(N, k)
    odd_total = (N + 1) // 2
    even_total = N // 2
    odd_rows = []
    for j in range(k + 1):
        prob = comb(odd_total, j) * comb(even_total, k - j) / total_C
        obs = sum(1 for r in records if sum(1 for x in r["numbers"] if x % 2) == j)
        odd_rows.append((j, k - j, obs, prob))
    low_total = cfg["low_max"]
    high_total = N - low_total
    low_rows = []
    for j in range(k + 1):
        prob = comb(low_total, j) * comb(high_total, k - j) / total_C
        obs = sum(1 for r in records if sum(1 for x in r["numbers"] if x <= low_total) == j)
        low_rows.append((j, k - j, obs, prob))
    sums = [sum(r["numbers"]) for r in records]
    consec_prob = 1 - comb(N - k + 1, k) / total_C
    consec_obs = sum(1 for r in records if any(b - a == 1 for a, b in zip(sorted(r["numbers"]), sorted(r["numbers"])[1:])))
    return {
        "draws": draws, "counts": counts, "bonus_counts": bonus_counts, "since": since,
        "expected": expected, "sd": sd, "lo": lo, "hi": hi, "outside": outside,
        "odd_rows": odd_rows, "low_rows": low_rows, "low_total": low_total,
        "sum_min": min(sums) if sums else None, "sum_max": max(sums) if sums else None,
        "sum_mean": (sum(sums) / len(sums)) if sums else None,
        "sum_theory": k * (N + 1) / 2,
        "consec_prob": consec_prob, "consec_obs": consec_obs,
    }


def pct(x):
    return f"{x * 100:.1f}%"


def split_table(rows, draws, left_label, right_label):
    trs = "".join(
        f"<tr><td>{a} {left_label} / {b} {right_label}</td><td>{obs}</td><td>{prob * draws:.1f}</td><td>{pct(prob)}</td></tr>"
        for a, b, obs, prob in rows
    )
    return (f'<div class="table-wrap"><table><thead><tr><th>Split</th><th>Draws seen here</th>'
            f'<th>Expected in {draws} draws</th><th>Long-run share</th></tr></thead><tbody>{trs}</tbody></table></div>')


def freq_grid(st, N):
    tiles = []
    for i in range(1, N + 1):
        c = st["counts"][i]
        s = st["since"][i]
        since_txt = "not yet seen" if s is None else ("in latest draw" if s == 0 else f"{s} draw{'s' if s != 1 else ''} ago")
        tiles.append(f'<div class="freq-tile"><span class="ball ball-neutral ball-sm">{i}</span>'
                     f'<span class="font-bold">{c}×</span><span class="text-[11px] text-slate-500">{since_txt}</span></div>')
    return f'<div class="freq-grid">{"".join(tiles)}</div>'


# ---------------------------------------------------------------------------
# Archive pages
# ---------------------------------------------------------------------------
def expected_latest_draw(today, weekdays):
    d = today.date() - timedelta(days=1)
    while d.weekday() not in weekdays:
        d -= timedelta(days=1)
    return d


def archive_intro(game_key, records):
    first = long_date(parse_date(records[0]["date"])) if records else "—"
    if game_key == "lotto_max":
        return f"""<h1>Lotto Max results archive</h1>
<p class="lead">Every Lotto Max draw recorded on this site since {first}, with the winning numbers, bonus number and the jackpot information that was published for each draw, followed by descriptive statistics calculated from the same data.</p>
<p>Lotto Max is drawn every Tuesday and Friday. Since April 2026, a $6 play gives you four selections of seven numbers from 1 to 52: you choose one line (or take a Quick Pick) and the terminal adds three Quick Pick lines. Seven main numbers and a bonus number are drawn. Matching all seven on one line wins or shares the main jackpot, which starts at $10 million and is capped at $90 million. Every draw also has $100,000 MaxPlus prizes, and once the jackpot passes $50 million there are $1 million MaxMillions prizes as well. The full mechanics are in our <a href="/lotto-max-maxmillions-explained.html">Lotto Max and MaxMillions guide</a>.</p>
<p>How this archive is built: a script reads Western Canada Lottery Corporation's public winning-number page after each draw night. A row is only added when the date, the weekday and the count of numbers all check out, so a missing row means the result could not be verified automatically, not that a draw did not happen. The jackpot column comes from the jackpot figure WCLC advertised before that draw; it was recorded starting in October 2026, so earlier rows show a dash. Always confirm a ticket against <a href="https://www.wclc.com/winning-numbers/lotto-max-extra.htm" rel="noopener">WCLC</a> or your own provincial lottery before you rely on it.</p>"""
    return f"""<h1>Lotto 6/49 results archive</h1>
<p class="lead">Every Lotto 6/49 draw recorded on this site since {first}: the Classic Draw numbers, the bonus number and what happened in the Gold Ball draw, followed by descriptive statistics calculated from the same data.</p>
<p>Lotto 6/49 is drawn every Wednesday and Saturday. A $3 play has two parts. In the Classic Draw you pick six numbers from 1 to 49; matching all six wins or shares a fixed $5 million jackpot, and smaller prizes start at two numbers plus the bonus. Each play also carries a 10-digit Gold Ball number. One Gold Ball number is drawn every time, so somebody always wins either the guaranteed $1 million (white ball) or the Gold Ball jackpot (gold ball), which starts at $10 million and grows by $2 million after every white ball. Our <a href="/lotto-649-gold-ball-explained.html">Gold Ball guide</a> explains the drum and the odds.</p>
<p>How this archive is built: a script reads Western Canada Lottery Corporation's public winning-number page after each draw night and adds a row only when the date, weekday and numbers pass validation. The Gold Ball jackpot column is calculated from WCLC's published rule and the published results (for example, the gold ball drawn on September 19, 2026 paid $32,000,000, which fixes the value of the eleven white-ball draws before it). Rows where it cannot be worked out show a dash. Confirm any ticket with <a href="https://www.wclc.com/winning-numbers/lotto-649-extra.htm" rel="noopener">WCLC</a> or your provincial lottery.</p>"""


def render_archive(game_key, history, today):
    cfg = GAMES[game_key]
    records = history.get(game_key) or []
    st = game_stats(records, cfg)
    N, k, name = cfg["N"], cfg["k"], cfg["name"]
    parts = [f'<section class="card prose-lh">{archive_intro(game_key, records)}</section>']

    if records:
        latest = records[-1]
        ldt = parse_date(latest["date"])
        stale = ldt.date() < expected_latest_draw(today, cfg["draw_weekdays"])
        stale_html = ('<p class="notice">The most recent draw has not been verified here yet. Check the official page for the latest numbers.</p>' if stale else "")
        parts.append(f"""<section class="card mt-6">
<h2 class="section-title">Latest verified draw: {esc(long_date(ldt))}</h2>
<div class="my-4">{balls_html(latest['numbers'], latest.get('bonus'), cfg['ball_class'])}</div>
<p class="text-sm text-slate-600">The grey ball is the bonus number. {stale_html}</p>
</section>""")

    d = st["draws"]
    if d:
        most = sorted(st["counts"].items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        least = sorted(st["counts"].items(), key=lambda kv: (kv[1], kv[0]))[:5]
        never = [i for i, c in st["counts"].items() if c == 0]
        most_txt = ", ".join(f"{i} ({c}×)" for i, c in most)
        least_txt = ", ".join(f"{i} ({c}×)" for i, c in least)
        never_txt = (f" {len(never)} numbers have not appeared at all in this archive yet ({', '.join(map(str, never))}); with only {d} draws that is expected — the chance a given number misses {d} draws in a row is about {pct((1 - k / N) ** d)}." if never else "")
        parts.append(f"""<section class="card prose-lh mt-6">
<h2>Number frequency across {d} recorded draws</h2>
<p>Each draw shows {k} main numbers out of {N}, so in {d} draws each number would appear about <strong>{st['expected']:.1f} times</strong> on average. Random variation around that average is normal: roughly 95% of numbers should land between {max(st['lo'], 0):.1f} and {st['hi']:.1f} appearances (two standard deviations either side). In this archive {len(st['outside'])} of {N} numbers fall outside that band{(' (' + ', '.join(map(str, st['outside'])) + ')') if st['outside'] else ''}, which is in line with chance.</p>
<p>Most frequent so far: {most_txt}. Least frequent: {least_txt}.{never_txt} None of this changes the next draw: every number has exactly the same chance each time. See <a href="/hot-cold-explained.html">why hot and cold numbers do not predict anything</a>.</p>
{freq_grid(st, N)}
<p class="text-xs text-slate-500 mt-2">Counts include main numbers only (not the bonus). "Draws ago" counts back from the latest draw in this archive.</p>
</section>""")

        parts.append(f"""<section class="card prose-lh mt-6">
<h2>Odd/even and low/high patterns</h2>
<p>The table compares how often each odd/even split has shown up here with the exact long-run probability for a {k}-from-{N} draw. Expected counts come from straight combinatorics (how many ways to pick that many odd and even numbers, divided by all {comb(N, k):,} possible combinations), not from past results.</p>
{split_table(st['odd_rows'], d, 'odd', 'even')}
<p>The same comparison for low numbers (1–{st['low_total']}) against high numbers ({st['low_total'] + 1}–{N}):</p>
{split_table(st['low_rows'], d, 'low', 'high')}
<p>Balanced splits are common simply because there are many more ways to make them, not because the drum prefers them. An all-odd ticket and a three-odd ticket are equally likely to win if they are specific combinations; the "balanced" category just contains more combinations.</p>
<h3>Sums and consecutive numbers</h3>
<p>The sum of the {k} main numbers has ranged from {st['sum_min']} to {st['sum_max']} here, averaging {st['sum_mean']:.1f}. Over the long run the average sum is exactly {st['sum_theory']:.1f}. At least one pair of consecutive numbers (such as 14 and 15) appeared in {st['consec_obs']} of {d} draws ({pct(st['consec_obs'] / d)}); the long-run probability is {pct(st['consec_prob'])}, which surprises many people who avoid consecutive numbers on purpose.</p>
</section>""")

    if game_key == "lotto_649" and records:
        jps = gold_ball_derivation(records)
        golds = [(r, jps[i]) for i, r in enumerate(records) if (r.get("gold_ball") or {}).get("ball") == "Gold"]
        gold_txt = "; ".join(f"{long_date(parse_date(r['date']))} ({money((r.get('gold_ball') or {}).get('prize') or j)})" for r, j in golds) or "none yet"
        up = (history.get("upcoming") or {}).get("lotto_649") or {}
        up_txt = ""
        if up.get("date") and up["date"] >= today.strftime("%Y-%m-%d") and up.get("gold_ball_jackpot"):
            udt = datetime.strptime(up["date"], "%Y-%m-%d")
            br = up.get("balls_remaining")
            up_txt = (f"<p>For the draw on <strong>{esc(long_date(udt))}</strong>, WCLC lists a Gold Ball jackpot of <strong>{money(up['gold_ball_jackpot'])}</strong>"
                      + (f" with {br} balls in the drum, so the chance that the gold ball comes out that night is 1 in {br}." if br else ".") + "</p>")
        parts.append(f"""<section class="card prose-lh mt-6">
<h2>Gold Ball draw tracker</h2>
{up_txt}
<p>Gold Ball wins recorded in this archive: {gold_txt}.</p>
<p>After each gold-ball win the drum is reset to 30 balls (29 white, 1 gold) and the jackpot to $10 million. White balls are not put back, so the gold ball must appear within 30 draws, and the largest possible Gold Ball jackpot under the current rule is $68 million (the 30th draw of a cycle). A useful consequence: looking forward from a reset, the gold ball is equally likely to be drawn in any of the 30 draws of the cycle (1 in 30 each), so the average jackpot when it is finally won works out to $39 million. The odds that <em>your</em> ticket wins either the $1 million or the jackpot are one in the number of Gold Ball selections sold for that draw.</p>
</section>""")

    # Full table, newest first
    rows = []
    jps = gold_ball_derivation(records) if game_key == "lotto_649" else None
    for i in range(len(records) - 1, -1, -1):
        r = records[i]
        dt = parse_date(r["date"])
        cells = [f'<td class="whitespace-nowrap">{esc(short_date(dt))}</td>',
                 f"<td>{balls_html(r['numbers'], None, cfg['ball_class'], small=True)}</td>",
                 f'<td><span class="ball ball-bonus ball-sm">{r.get("bonus")}</span></td>']
        if game_key == "lotto_649":
            gb = r.get("gold_ball") or {}
            ball = gb.get("ball")
            if ball == "Gold":
                res = f"Gold ball — jackpot won ({money(gb.get('prize') or jps[i])})"
            elif ball == "White":
                res = "White ball — $1 million prize"
            else:
                res = "—"
            cells.append(f"<td>{esc(res)}</td>")
            cells.append(f"<td>{money(jps[i])}</td>")
        else:
            jp = r.get("jackpot")
            extra = []
            if r.get("maxmillions"):
                extra.append(f"{r['maxmillions']} × $1M MaxMillions")
            if r.get("maxplus"):
                extra.append(f"{r['maxplus']} × $100K MaxPlus")
            cells.append(f"<td>{money(jp) if jp else '—'}</td>")
            cells.append(f"<td>{esc(', '.join(extra)) if extra else '—'}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    if game_key == "lotto_649":
        head = "<th>Draw date</th><th>Classic Draw numbers</th><th>Bonus</th><th>Gold Ball draw</th><th>Gold Ball jackpot</th>"
    else:
        head = "<th>Draw date</th><th>Winning numbers</th><th>Bonus</th><th>Advertised jackpot</th><th>Extra prize draws</th>"
    parts.append(f"""<section class="card mt-6">
<h2 class="section-title">All recorded {esc(name)} draws ({len(records)})</h2>
<p class="text-sm text-slate-600 mb-3">Newest first. Numbers are sorted in ascending order, as published.</p>
<div class="table-wrap"><table class="draw-table"><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
</section>""")

    parts.append(f"""<section class="card prose-lh mt-6">
<h2>What this page cannot tell you</h2>
<p>It cannot tell you what will be drawn next. Lotto draws are certified random and independent; past frequencies, splits and sums describe what already happened and nothing more. It also cannot confirm a prize: winning-ticket locations, prize shares and claim rules are published by the lottery corporations. For that, use the official <a href="{cfg['official']}" rel="noopener">WCLC {esc(name)} page</a>, BCLC's site or app in British Columbia, or your own provincial operator, and read our guide to <a href="/how-to-claim-lottery-prize-bc.html">checking and claiming a prize</a>.</p>
<p>Found a row that disagrees with an official result? Please <a href="/contact.html">let us know</a> — corrections are made as soon as they are confirmed.</p>
</section>""")

    title = f"{name} results archive and statistics"
    desc = (f"All {name} winning numbers recorded since {long_date(parse_date(records[0]['date'])) if records else '2026'}, "
            f"with bonus numbers, jackpot details and plain-language statistics. Unofficial; verify with your lottery.")
    return layout(cfg["path"], title, desc, "\n".join(parts), active=cfg["path"])


# ---------------------------------------------------------------------------
# Homepage
# ---------------------------------------------------------------------------
def home_game_card(game_key, history, today):
    cfg = GAMES[game_key]
    records = history.get(game_key) or []
    if not records:
        return ""
    latest = records[-1]
    ldt = parse_date(latest["date"])
    up = (history.get("upcoming") or {}).get(game_key) or {}
    next_html = ""
    if up.get("date") and up["date"] >= today.strftime("%Y-%m-%d"):
        udt = datetime.strptime(up["date"], "%Y-%m-%d")
        if game_key == "lotto_max" and up.get("jackpot"):
            bits = [f"Jackpot {money(up['jackpot'])}"]
            if up.get("maxmillions"):
                bits.append(f"{up['maxmillions']} × $1 million MaxMillions")
            if up.get("maxplus"):
                bits.append(f"{up['maxplus']} × $100,000 MaxPlus")
            next_html = f"<p class='text-sm mt-3'><strong>Next draw, {esc(long_date(udt))}:</strong> {esc(', '.join(bits))} (as advertised by WCLC).</p>"
        elif game_key == "lotto_649" and up.get("gold_ball_jackpot"):
            br = up.get("balls_remaining")
            next_html = (f"<p class='text-sm mt-3'><strong>Next draw, {esc(long_date(udt))}:</strong> Classic jackpot $5 million; Gold Ball jackpot {money(up['gold_ball_jackpot'])}"
                         + (f" with {br} balls left in the drum" if br else "") + " (as advertised by WCLC).</p>")
    extra = ""
    if game_key == "lotto_649":
        gb = latest.get("gold_ball") or {}
        if gb.get("ball") == "White":
            extra = "<p class='text-sm text-slate-600'>Gold Ball draw: white ball, so the guaranteed $1 million prize was won.</p>"
        elif gb.get("ball") == "Gold":
            extra = f"<p class='text-sm text-slate-600'>Gold Ball draw: the gold ball was drawn and the jackpot ({money(gb.get('prize'))}) was won.</p>"
    stale = ldt.date() < expected_latest_draw(today, cfg["draw_weekdays"])
    stale_html = "<p class='notice'>The most recent draw has not been verified here yet — check the official page.</p>" if stale else ""
    recent = "".join(
        f"<li class='flex flex-wrap items-center gap-2 py-1'><span class='w-32 text-sm text-slate-600'>{esc(short_date(parse_date(r['date'])))}</span>{balls_html(r['numbers'], r.get('bonus'), cfg['ball_class'], small=True)}</li>"
        for r in reversed(records[-5:-1])
    )
    return f"""<section class="card">
<h2 class="section-title">{esc(cfg['name'])} — {esc(long_date(ldt))}</h2>
<div class="my-4">{balls_html(latest['numbers'], latest.get('bonus'), cfg['ball_class'])}</div>
{extra}{next_html}{stale_html}
<h3 class="font-bold text-slate-800 mt-4">Previous draws</h3>
<ul class="mt-1">{recent}</ul>
<p class="mt-3 text-sm"><a href="{cfg['path']}">Full {esc(cfg['name'])} archive and statistics →</a> · <a href="{cfg['official']}" rel="noopener">Official WCLC page</a></p>
</section>"""


def render_index(history, today):
    guide_cards = "".join(
        f'<a href="/{s}.html" class="guide-card"><h3 class="font-bold text-slate-900">{esc(t)}</h3>'
        f'<p class="text-sm text-slate-600 mt-1">{esc(d)}</p></a>'
        for s, t, d in GUIDES
    )
    body = f"""<section class="card prose-lh">
<h1>Lotto Max and Lotto 6/49 results, explained in plain language</h1>
<p class="lead">lottohelper.ca is an independent, unofficial reference run from British Columbia. It keeps a clean archive of published Lotto Max and Lotto 6/49 results and explains how the games, prizes, claims and odds really work — without selling tickets or pretending to predict the next draw.</p>
<p>Results below are copied from the public winning-number pages of the Western Canada Lottery Corporation after each draw night and only appear once the date and numbers pass automatic checks. The archives keep every verified draw together with statistics that describe what has happened so far. The guides cover the questions players actually ask: how MaxMillions and the Gold Ball work, how to claim a prize in BC, whether winnings are taxed, what Extra and Encore are, and how to spot a lottery scam.</p>
<p>One thing never changes no matter what any chart shows: a Lotto 6/49 line has a 1 in 13,983,816 chance of matching all six numbers, and a $6 Lotto Max play has about a 1 in 33,446,140 chance at the main jackpot. Play for entertainment, within a budget — see <a href="/responsible-play.html">responsible play</a>.</p>
</section>
<div class="grid gap-6 md:grid-cols-2 mt-6">
{home_game_card('lotto_max', history, today)}
{home_game_card('lotto_649', history, today)}
</div>
<section class="mt-8">
<h2 class="text-2xl font-black text-slate-900 mb-1">Guides</h2>
<p class="text-sm text-slate-600 mb-4">Written by NextGen, British Columbia. Facts checked against BCLC, WCLC, OLG, CRA and Canadian Anti-Fraud Centre pages.</p>
<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{guide_cards}</div>
</section>
<section class="card prose-lh mt-8">
<h2>How this site works</h2>
<p>A small script runs every night after midnight Pacific time. It reads the official results, checks that each draw date falls on the right weekday and that the right count of numbers is present, and only then updates this page and the two results archives. If anything fails a check, yesterday's verified data stays in place — figures are never guessed. Jackpot amounts shown for upcoming draws are the ones WCLC advertises and can change; your provincial lottery has the final word.</p>
<p>We are not affiliated with BCLC, WCLC, OLG, Loto-Québec, Atlantic Lottery or the Interprovincial Lottery Corporation. Game names belong to their owners and are used only to identify the draws. Questions or corrections: see the <a href="/contact.html">contact page</a>. More about the project is on the <a href="/about.html">about page</a>.</p>
</section>"""
    return layout("/", "Lotto Max & Lotto 6/49 results and guides for Canada | lottohelper.ca",
                  "Independent archive of Lotto Max and Lotto 6/49 results with plain-language guides to MaxMillions, Gold Ball, prize claims in BC, taxes and lottery scams. No predictions, no ticket sales.",
                  body, active="/")


# ---------------------------------------------------------------------------
# Sitemap with real lastmod dates
# ---------------------------------------------------------------------------
def page_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_site(history, today):
    pages = {}  # url path -> (file, html)
    pages["/"] = ("index.html", render_index(history, today))
    for key, cfg in GAMES.items():
        pages[cfg["path"]] = (cfg["path"].lstrip("/"), render_archive(key, history, today))
    pages["/guides.html"] = ("guides.html", render_guides_index())
    for slug, meta, body in load_content_pages():
        pages[f"/{slug}.html"] = (f"{slug}.html", render_content_page(slug, meta, body))

    for path, (fname, text) in pages.items():
        write_file(fname, text)
    write_file("404.html", render_404())

    # lastmod: a page's date only moves when its rendered HTML actually changes.
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
    print(f"[INFO] Built {len(pages)} pages + 404.html; sitemap.xml has {len(pages)} URLs.")
