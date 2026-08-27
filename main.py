import json
import random
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

WCLC_649_URL = "https://www.wclc.com/winning-numbers/lotto-649-extra.htm?channel=print"
WCLC_MAX_URL = "https://www.wclc.com/winning-numbers/lotto-max-extra.htm?channel=print"
WCLC_HOME_URL = "https://www.wclc.com/home.htm"

WCLC_MAX_PRIZE_PAGE = "https://www.wclc.com/winning-numbers/lotto-max-extra.htm"
WCLC_649_PRIZE_PAGE = "https://www.wclc.com/winning-numbers/lotto-649-extra.htm"

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DATE_PATTERN = r'((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+\w+\s+\d{1,2},\s+\d{4})'

HISTORY_FILE = "draw_history.json"
HISTORY_WINDOW_DAYS = 183
MIN_DRAWS_FOR_LIVE_STATS = 15

SEED_MAX_FREQUENCIES = {
    "1": 8, "2": 6, "3": 9, "4": 11, "5": 7, "6": 10, "7": 8, "8": 5, "9": 7, "10": 9,
    "11": 6, "12": 8, "13": 7, "14": 10, "15": 12, "16": 8, "17": 9, "18": 11, "19": 13, "20": 6,
    "21": 10, "22": 7, "23": 8, "24": 9, "25": 11, "26": 8, "27": 6, "28": 10, "29": 7, "30": 9,
    "31": 8, "32": 5, "33": 7, "34": 6, "35": 10, "36": 8, "37": 7, "38": 9, "39": 8, "40": 11,
    "41": 6, "42": 7, "43": 8, "44": 10, "45": 9, "46": 6, "47": 7, "48": 8, "49": 5, "50": 8,
    "51": 7, "52": 6
}

SEED_649_FREQUENCIES = {
    "1": 7, "2": 9, "3": 6, "4": 8, "5": 10, "6": 8, "7": 9, "8": 5, "9": 7, "10": 11,
    "11": 8, "12": 6, "13": 9, "14": 7, "15": 10, "16": 6, "17": 8, "18": 7, "19": 9, "20": 5,
    "21": 8, "22": 11, "23": 6, "24": 7, "25": 9, "26": 8, "27": 10, "28": 7, "29": 8, "30": 6,
    "31": 9, "32": 7, "33": 8, "34": 10, "35": 6, "36": 9, "37": 7, "38": 8, "39": 5, "40": 8,
    "41": 7, "42": 9, "43": 6, "44": 8, "45": 10, "46": 7, "47": 8, "48": 6, "49": 7
}

class ScrapeError(Exception):
    pass

class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = False

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

def html_to_text(html):
    parser = _TextExtractor()
    parser.feed(html)
    text = " ".join(parser.parts)
    return re.sub(r"\s+", " ", text).strip()

def fetch_text(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as res:
        raw_html = res.read().decode("utf-8", errors="ignore")
    return html_to_text(raw_html)

def parse_draw_date(date_str):
    return datetime.strptime(date_str, "%A, %B %d, %Y")

def validate_draw_date(draw_dt, today_dt, expected_weekdays, max_age_days=4):
    age = (today_dt.date() - draw_dt.date()).days
    if age < 0 or age > max_age_days:
        raise ScrapeError(f"Draw date out of expected range: {draw_dt.date()} (today={today_dt.date()}, age={age}d)")
    if draw_dt.weekday() not in expected_weekdays:
        raise ScrapeError(f"Draw date weekday mismatch: {draw_dt.date()} is {WEEKDAY_NAMES[draw_dt.weekday()]}")

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {"lotto_max": [], "lotto_649": []}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"lotto_max": [], "lotto_649": []}
    data.setdefault("lotto_max", [])
    data.setdefault("lotto_649", [])
    return data

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def prune_history(records, today_dt, window_days=HISTORY_WINDOW_DAYS):
    kept = []
    for rec in records:
        try:
            rec_dt = parse_draw_date(rec["date"])
        except Exception:
            continue
        if (today_dt.date() - rec_dt.date()).days <= window_days:
            kept.append(rec)
    kept.sort(key=lambda r: parse_draw_date(r["date"]))
    return kept

def add_draw_to_history(history, game_key, draw_date_str, numbers, bonus, today_dt):
    records = history.get(game_key, [])
    records = [r for r in records if r.get("date") != draw_date_str]
    records.append({"date": draw_date_str, "numbers": numbers, "bonus": bonus})
    history[game_key] = prune_history(records, today_dt)
    return history

def compute_frequencies_from_history(records, total_numbers):
    counts = {str(n): 0 for n in range(1, total_numbers + 1)}
    for rec in records:
        for n in rec.get("numbers", []):
            key = str(n)
            if key in counts:
                counts[key] += 1
    return counts

def resolve_frequencies(history_records, total_numbers, seed_frequencies):
    if len(history_records) >= MIN_DRAWS_FOR_LIVE_STATS:
        return compute_frequencies_from_history(history_records, total_numbers), "live", len(history_records)
    return dict(seed_frequencies), "seed", len(history_records)

def parse_649(text, today_dt):
    classic_idx = text.find("CLASSIC DRAW")
    if classic_idx == -1:
        raise ScrapeError("649: 'CLASSIC DRAW' marker not found on page")

    date_matches = list(re.finditer(DATE_PATTERN, text[:classic_idx]))
    if not date_matches:
        raise ScrapeError("649: no date header found before CLASSIC DRAW")
    draw_date_str = date_matches[-1].group(1)
    draw_dt = parse_draw_date(draw_date_str)
    validate_draw_date(draw_dt, today_dt, expected_weekdays=[2, 5])

    gold_idx = text.find("GOLD BALL DRAW", classic_idx)
    segment_end = gold_idx if gold_idx != -1 else classic_idx + 400
    segment = text[classic_idx:segment_end]

    bonus_match = re.search(r"Bonus\s*(\d{1,2})", segment)
    if not bonus_match:
        raise ScrapeError(f"649: bonus number not found in segment: {segment!r}")
    bonus_num = int(bonus_match.group(1))

    segment_wo_bonus = re.sub(r"Bonus\s*\d{1,2}", "", segment)
    nums = [int(n) for n in re.findall(r"\b(\d{1,2})\b", segment_wo_bonus) if 1 <= int(n) <= 49]
    winning_numbers = nums[:6]

    if len(winning_numbers) != 6 or len(set(winning_numbers)) != 6:
        raise ScrapeError(f"649: malformed winning numbers {winning_numbers}")

    ball_events = re.findall(r"Ball Drawn:\s*(White|Gold)", text)
    latest_ball_outcome = ball_events[0] if ball_events else "White"

    white_streak = 0
    for outcome in ball_events:
        if outcome == "White":
            white_streak += 1
        else:
            break

    # Gold가 과거 목록에 없더라도 에러를 내지 않고 추산값을 계산
    next_gold_ball_jackpot = 10_000_000 + 2_000_000 * white_streak

    return {
        "winning_numbers": sorted(winning_numbers),
        "bonus": bonus_num,
        "draw_date": draw_date_str,
        "latest_ball_outcome": latest_ball_outcome,
        "next_gold_ball_jackpot": next_gold_ball_jackpot,
    }

def parse_max(text, today_dt):
    date_matches = list(re.finditer(DATE_PATTERN, text))
    if not date_matches:
        raise ScrapeError("Max: no date header found on page")
    first_match = date_matches[0]
    draw_date_str = first_match.group(1)
    draw_dt = parse_draw_date(draw_date_str)
    validate_draw_date(draw_dt, today_dt, expected_weekdays=[1, 4])

    end_idx = text.find("Exact Match Only", first_match.end())
    segment_end = end_idx if end_idx != -1 else first_match.end() + 400
    segment = text[first_match.end():segment_end]

    bonus_match = re.search(r"Bonus\s*(\d{1,2})", segment)
    if not bonus_match:
        raise ScrapeError(f"Max: bonus number not found in segment: {segment!r}")
    bonus_num = int(bonus_match.group(1))

    segment_wo_bonus = re.sub(r"Bonus\s*\d{1,2}", "", segment)
    nums = [int(n) for n in re.findall(r"\b(\d{1,2})\b", segment_wo_bonus) if 1 <= int(n) <= 52]
    winning_numbers = nums[:7]

    if len(winning_numbers) != 7 or len(set(winning_numbers)) != 7:
        raise ScrapeError(f"Max: malformed winning numbers {winning_numbers}")

    return {
        "winning_numbers": sorted(winning_numbers),
        "bonus": bonus_num,
        "draw_date": draw_date_str,
    }

def parse_649_all(text, today_dt):
    results = []
    classic_positions = [m.start() for m in re.finditer("CLASSIC DRAW", text)]
    ball_events_all = re.findall(r"Ball Drawn:\s*(White|Gold)", text)

    for idx, classic_idx in enumerate(classic_positions):
        date_matches = list(re.finditer(DATE_PATTERN, text[:classic_idx]))
        if not date_matches:
            continue
        draw_date_str = date_matches[-1].group(1)
        try:
            draw_dt = parse_draw_date(draw_date_str)
        except Exception:
            continue
        if draw_dt.weekday() not in (2, 5) or draw_dt.date() > today_dt.date():
            continue

        gold_idx = text.find("GOLD BALL DRAW", classic_idx)
        segment_end = gold_idx if gold_idx != -1 else classic_idx + 400
        segment = text[classic_idx:segment_end]

        bonus_match = re.search(r"Bonus\s*(\d{1,2})", segment)
        if not bonus_match:
            continue
        bonus_num = int(bonus_match.group(1))

        segment_wo_bonus = re.sub(r"Bonus\s*\d{1,2}", "", segment)
        nums = [int(n) for n in re.findall(r"\b(\d{1,2})\b", segment_wo_bonus) if 1 <= int(n) <= 49]
        winning_numbers = nums[:6]
        if len(winning_numbers) != 6 or len(set(winning_numbers)) != 6:
            continue

        outcome = ball_events_all[idx] if idx < len(ball_events_all) else None

        results.append({
            "draw_date": draw_date_str,
            "winning_numbers": sorted(winning_numbers),
            "bonus": bonus_num,
            "ball_outcome": outcome,
        })
    return results

def parse_max_all(text, today_dt):
    results = []
    date_matches = list(re.finditer(DATE_PATTERN, text))

    for dm in date_matches:
        draw_date_str = dm.group(1)
        try:
            draw_dt = parse_draw_date(draw_date_str)
        except Exception:
            continue
        if draw_dt.weekday() not in (1, 4) or draw_dt.date() > today_dt.date():
            continue

        end_idx = text.find("Exact Match Only", dm.end())
        segment_end = end_idx if end_idx != -1 else dm.end() + 400
        segment = text[dm.end():segment_end]

        bonus_match = re.search(r"Bonus\s*(\d{1,2})", segment)
        if not bonus_match:
            continue
        bonus_num = int(bonus_match.group(1))

        segment_wo_bonus = re.sub(r"Bonus\s*\d{1,2}", "", segment)
        nums = [int(n) for n in re.findall(r"\b(\d{1,2})\b", segment_wo_bonus) if 1 <= int(n) <= 52]
        winning_numbers = nums[:7]
        if len(winning_numbers) != 7 or len(set(winning_numbers)) != 7:
            continue

        results.append({
            "draw_date": draw_date_str,
            "winning_numbers": sorted(winning_numbers),
            "bonus": bonus_num,
        })
    return results

def fetch_home_jackpots(text, today_dt):
    date_re = DATE_PATTERN

    gb_pattern = re.compile(
        r"GOLD BALL JACKPOT\s*\$\s*(\d+)\s*Million.*?(\d+)\s*Balls Remaining.*?" + date_re,
        re.DOTALL,
    )
    gb_match = gb_pattern.search(text)
    if not gb_match:
        raise ScrapeError("Home: Gold Ball jackpot ticker block not found")

    gb_millions = int(gb_match.group(1))
    balls_remaining = int(gb_match.group(2))
    gb_next_date_str = gb_match.group(3)
    gb_next_dt = parse_draw_date(gb_next_date_str)

    if gb_next_dt.date() < today_dt.date():
        raise ScrapeError(f"Home: Gold Ball next draw date {gb_next_dt.date()} is in the past")
    if gb_next_dt.weekday() not in (2, 5):
        raise ScrapeError(f"Home: Gold Ball next draw date {gb_next_dt.date()} is not Wed/Sat")

    max_pattern = re.compile(
        r"\$\s*(\d+)\s*Million\s*(\d+)\s*x\s*\$100,000\s*" + date_re
    )
    max_match = max_pattern.search(text, gb_match.end())
    if not max_match:
        raise ScrapeError("Home: Lotto Max jackpot ticker block not found")

    max_millions = int(max_match.group(1))
    maxplus_count = int(max_match.group(2))
    max_next_date_str = max_match.group(3)
    max_next_dt = parse_draw_date(max_next_date_str)

    if max_next_dt.date() < today_dt.date():
        raise ScrapeError(f"Home: Lotto Max next draw date {max_next_dt.date()} is in the past")
    if max_next_dt.weekday() not in (1, 4):
        raise ScrapeError(f"Home: Lotto Max next draw date {max_next_dt.date()} is not Tue/Fri")

    return {
        "gold_ball_jackpot": gb_millions * 1_000_000,
        "gold_ball_next_draw": gb_next_date_str,
        "gold_ball_balls_remaining": balls_remaining,
        "max_jackpot": max_millions * 1_000_000,
        "max_next_draw": max_next_date_str,
        "max_maxplus_count": maxplus_count,
    }

def generate_ai_numbers(total, count):
    return sorted(random.sample(range(1, total + 1), count))

def build_deep_analysis_note(game_name, draw_date_str, winning_nums, ai_nums, jackpot_text, prov_status):
    even_count = sum(1 for n in winning_nums if n % 2 == 0)
    odd_count = len(winning_nums) - even_count
    ai_even = sum(1 for n in ai_nums if n % 2 == 0)
    ai_odd = len(ai_nums) - ai_even
    low_bound = 25 if game_name == "Lotto 6/49" else 26
    low_count = sum(1 for n in winning_nums if n <= low_bound)
    high_count = len(winning_nums) - low_count

    return (
        f"### 1. Official Draw Breakdown (Draw Date: {draw_date_str})\n"
        f"In the official {game_name} drawing conducted on {draw_date_str}, the verified winning combination was {', '.join(map(str, winning_nums))}. "
        f"Jackpot: {jackpot_text}. Status: {prov_status}.\n\n"
        f"### 2. Parity & Distribution Matrix Analysis\n"
        f"Evaluating the official combination yields {odd_count} Odd numbers and {even_count} Even numbers, "
        f"with {high_count} higher-bracket numbers and {low_count} lower-bracket numbers.\n\n"
        f"### 3. AI Frequency-Weighted Line Strategy\n"
        f"Our algorithmic model evaluated historical frequency clusters to formulate the recommended line: {', '.join(map(str, ai_nums))}. "
        f"This combination maintains a {ai_odd}:{ai_even} Odd/Even parity distribution.\n\n"
        f"### 4. Strategic Observations\n"
        f"Numbers are drawn independently and randomly. Historical frequency does not predict future outcomes. "
        f"Please play responsibly. For analytical and entertainment purposes only."
    )

import html as html_escape_module
TEMPLATE_PATH = "index_template.html"
INDEX_OUTPUT_PATH = "index.html"

def get_freq_thresholds(freq_dict):
    counts = [int(v) for v in freq_dict.values()] if freq_dict else []
    max_val = max(counts) if counts else 13
    min_val = min(counts) if counts else 5
    rng = (max_val - min_val) / 3
    return max_val - rng, min_val + rng

def freq_color_class(num, freq_dict, hot_thresh, cold_thresh):
    count = freq_dict.get(str(num), 7)
    if count >= hot_thresh:
        return "bg-red-600"
    if count <= cold_thresh:
        return "bg-sky-600"
    return "bg-emerald-600"

def render_balls_html(numbers, freq_dict, bonus=None):
    if not numbers:
        return ""
    hot_thresh, cold_thresh = get_freq_thresholds(freq_dict or {})
    parts = []
    for n in numbers:
        cls = freq_color_class(n, freq_dict or {}, hot_thresh, cold_thresh)
        parts.append(f'<div class="lotto-ball {cls}">{n}</div>')
    if bonus is not None:
        parts.append('<div class="ball-divider"></div>')
        cls = freq_color_class(bonus, freq_dict or {}, hot_thresh, cold_thresh)
        parts.append(
            f'<div class="lotto-ball lotto-ball-bonus {cls}" title="Official Bonus Number">{bonus}</div>'
        )
    return "".join(parts)

def render_freq_grid_html(freq_dict, total_numbers):
    freq_dict = freq_dict or {}
    hot_thresh, cold_thresh = get_freq_thresholds(freq_dict)
    tiles = []
    for i in range(1, total_numbers + 1):
        count = freq_dict.get(str(i), 7)
        if count >= hot_thresh:
            card_style, ball_color, badge_style = "border-red-300 bg-red-50/70", "bg-red-600", "bg-red-600 text-white"
        elif count <= cold_thresh:
            card_style, ball_color, badge_style = "border-sky-300 bg-sky-50/70", "bg-sky-600", "bg-sky-600 text-white"
        else:
            card_style, ball_color, badge_style = "border-emerald-300 bg-emerald-50/70", "bg-emerald-600", "bg-emerald-600 text-white"
        tiles.append(
            f'<div class="p-1.5 rounded-xl border flex flex-col items-center justify-center {card_style}">'
            f'<div class="lotto-ball-xs {ball_color} mb-1">{i}</div>'
            f'<span class="text-[10px] font-black px-1.5 py-0.5 rounded-md {badge_style}">{count}x</span></div>'
        )
    return "".join(tiles)

def linkify_html(text):
    if not text:
        return ""
    escaped = html_escape_module.escape(text, quote=False)
    return re.sub(
        r"(https?://[^\s]+)",
        r'<a href="\1" target="_blank" rel="noopener" class="underline decoration-dotted hover:text-white">\1</a>',
        escaped,
    )

def render_freq_subtitle(freq_source, freq_count):
    if freq_source == "live":
        return f"Live-calculated from the last {freq_count} verified draws (rolling ~6 months)"
    if freq_source == "seed":
        return (
            f"Reference snapshot — only {freq_count} verified draws recorded so far; "
            "switches to live data once enough draws accumulate"
        )
    return "Occurrence counts based on official national records"

def render_post_card_html(post):
    game = html_escape_module.escape(post.get("game", "Lotto"))
    title = html_escape_module.escape(post.get("title", ""))
    summary = html_escape_module.escape(post.get("summary", ""))
    post_id = html_escape_module.escape(post.get("id", ""))
    return (
        f'<div class="bg-white p-5 rounded-2xl shadow-sm border border-slate-200 hover:shadow-md transition cursor-pointer" '
        f'onclick="openPost(\'{post_id}\')">'
        f'<div class="flex items-center justify-between text-xs text-slate-400 font-medium mb-1.5">'
        f'<span class="bg-emerald-100 text-emerald-800 px-2.5 py-0.5 rounded font-bold">{game}</span>'
        f'<span class="text-teal-600 font-bold">Read Analysis →</span></div>'
        f'<h3 class="text-base font-bold text-slate-800 mb-1 hover:text-teal-700 transition">{title}</h3>'
        f'<p class="text-xs text-slate-500 leading-relaxed line-clamp-2">{summary}</p></div>'
    )

def replace_element_html(html_str, element_id, new_inner_html):
    pattern = re.compile(
        r'(<([a-zA-Z0-9]+)([^>]*\bid="' + re.escape(element_id) + r'"[^>]*)>)(.*?)(</\2>)',
        re.DOTALL,
    )
    new_html, count = pattern.subn(lambda m: m.group(1) + new_inner_html + m.group(5), html_str, count=1)
    if count == 0:
        raise ValueError(f"index_template.html: id={element_id!r} 요소를 찾지 못함")
    return new_html

def set_element_class(html_str, element_id, new_class_value):
    pattern = re.compile(r'(<[a-zA-Z0-9]+\s+id="' + re.escape(element_id) + r'"\s+class=")([^"]*)(")')
    new_html, count = pattern.subn(lambda m: m.group(1) + new_class_value + m.group(3), html_str, count=1)
    if count == 0:
        raise ValueError(f"index_template.html: id={element_id!r} class 속성을 찾지 못함")
    return new_html

def render_index_html(template_html, home_display, posts_list):
    out = template_html
    max_data = home_display["lotto_max"]
    l649_data = home_display["lotto_649"]

    is_stale = "[STALE" in (max_data.get("winner_province") or "") or "[STALE" in (l649_data.get("winner_province") or "")
    out = set_element_class(
        out, "stale-banner",
        "bg-amber-100 border-b border-amber-300 text-amber-900 text-xs sm:text-sm font-semibold text-center py-2 px-4"
        + ("" if is_stale else " hidden"),
    )

    out = replace_element_html(out, "max-jackpot", "EST. " + html_escape_module.escape(str(max_data.get("jackpot") or "Unavailable")))
    out = replace_element_html(out, "max-draw-date", "Last verified draw: " + html_escape_module.escape(str(max_data.get("draw_date") or "unknown")))
    out = replace_element_html(out, "max-prov-text", linkify_html(max_data.get("winner_province")))
    out = replace_element_html(out, "max-win-balls", render_balls_html(max_data.get("winning_numbers"), max_data.get("frequencies"), max_data.get("bonus")))
    out = replace_element_html(out, "max-balls", render_balls_html(generate_ai_numbers(52, 7), max_data.get("frequencies")))

    out = replace_element_html(out, "goldball-amount", html_escape_module.escape(str(l649_data.get("gold_ball") or "Unavailable")))
    out = replace_element_html(out, "l649-draw-date", "Last verified draw: " + html_escape_module.escape(str(l649_data.get("draw_date") or "unknown")))
    out = replace_element_html(out, "l649-prov-text", linkify_html(l649_data.get("winner_province")))
    out = replace_element_html(out, "l649-win-balls", render_balls_html(l649_data.get("winning_numbers"), l649_data.get("frequencies"), l649_data.get("bonus")))
    out = replace_element_html(out, "l649-balls", render_balls_html(generate_ai_numbers(49, 6), l649_data.get("frequencies")))

    out = replace_element_html(out, "freq-title", "Lotto Max (1-52)")
    out = replace_element_html(
        out, "freq-subtitle",
        html_escape_module.escape(render_freq_subtitle(max_data.get("frequency_source"), max_data.get("frequency_draws_counted", 0))),
    )
    out = replace_element_html(out, "freq-grid-container", render_freq_grid_html(max_data.get("frequencies"), 52))

    if posts_list:
        posts_html = "".join(render_post_card_html(p) for p in posts_list[:12])
    else:
        posts_html = '<div class="p-6 text-center text-slate-400 text-xs">No draw posts available.</div>'
    out = replace_element_html(out, "posts-container", posts_html)

    embedded_data = json.dumps(home_display, ensure_ascii=False).replace("</", "<\\/")
    embedded_posts = json.dumps(posts_list, ensure_ascii=False).replace("</", "<\\/")
    injection = (
        f"<script>window.__INITIAL_DISPLAY_DATA__ = {embedded_data}; "
        f"window.__INITIAL_POSTS__ = {embedded_posts};</script>\n    <script>"
    )
    out = out.replace("<script>", injection, 1)

    return out

def build_index_html(home_display, posts_list):
    if not os.path.exists(TEMPLATE_PATH):
        print(f"[WARN] {TEMPLATE_PATH} not found — skipping index.html rebuild.", file=sys.stderr)
        return
    try:
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            template_html = f.read()
        rendered = render_index_html(template_html, home_display, posts_list)
        with open(INDEX_OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(rendered)
        print("[INFO] index.html rebuilt with real data baked in.")
    except Exception as e:
        print(f"[WARN] index.html rebuild failed: {e}", file=sys.stderr)

def main():
    pst_offset = timedelta(hours=-7)
    today_dt = datetime.now(timezone.utc) + pst_offset
    today_date = today_dt.strftime("%Y-%m-%d")
    display_date = today_dt.strftime("%B %d, %Y")
    weekday = today_dt.weekday()

    display_path = "today_display.json"

    previous_data = None
    if os.path.exists(display_path):
        try:
            with open(display_path, "r", encoding="utf-8") as f:
                previous_data = json.load(f)
        except Exception:
            previous_data = None

    max_result = None
    l649_result = None
    max_error = None
    l649_error = None
    home_jackpots = None
    home_error = None

    try:
        max_text = fetch_text(WCLC_MAX_URL)
        max_result = parse_max(max_text, today_dt)
    except Exception as e:
        max_error = str(e)
        print(f"[WARN] Lotto Max scrape/validation failed: {max_error}", file=sys.stderr)

    try:
        l649_text = fetch_text(WCLC_649_URL)
        l649_result = parse_649(l649_text, today_dt)
    except Exception as e:
        l649_error = str(e)
        print(f"[WARN] Lotto 6/49 scrape/validation failed: {l649_error}", file=sys.stderr)

    history = load_history()
    if max_result:
        try:
            for draw in parse_max_all(max_text, today_dt):
                history = add_draw_to_history(
                    history, "lotto_max", draw["draw_date"],
                    draw["winning_numbers"], draw["bonus"], today_dt,
                )
        except Exception as e:
            print(f"[WARN] Max history backfill parse failed: {e}", file=sys.stderr)
    if l649_result:
        try:
            for draw in parse_649_all(l649_text, today_dt):
                history = add_draw_to_history(
                    history, "lotto_649", draw["draw_date"],
                    draw["winning_numbers"], draw["bonus"], today_dt,
                )
        except Exception as e:
            print(f"[WARN] 649 history backfill parse failed: {e}", file=sys.stderr)

    history["lotto_max"] = prune_history(history.get("lotto_max", []), today_dt)
    history["lotto_649"] = prune_history(history.get("lotto_649", []), today_dt)
    save_history(history)

    max_frequencies, max_freq_source, max_draw_count = resolve_frequencies(
        history["lotto_max"], 52, SEED_MAX_FREQUENCIES
    )
    l649_frequencies, l649_freq_source, l649_draw_count = resolve_frequencies(
        history["lotto_649"], 49, SEED_649_FREQUENCIES
    )

    try:
        home_text = fetch_text(WCLC_HOME_URL)
        home_jackpots = fetch_home_jackpots(home_text, today_dt)
    except Exception as e:
        home_error = str(e)
        print(f"[WARN] WCLC home jackpot ticker scrape failed: {home_error}", file=sys.stderr)

    # Lotto Max 데이터 구성
    if max_result:
        max_win_nums = max_result["winning_numbers"]
        max_bonus = max_result["bonus"]
        max_draw_date = max_result["draw_date"]

        if home_jackpots:
            max_jp = f"${home_jackpots['max_jackpot'] / 1_000_000:.0f} Million"
            max_prov = (
                f"Draw confirmed for {max_draw_date}. Next jackpot ({home_jackpots['max_next_draw']}): "
                f"{max_jp} ({home_jackpots['max_maxplus_count']} x $100,000 MaxPlus prizes). "
                f"Winning ticket location: see official WCLC prize breakdown — "
                f"{WCLC_MAX_PRIZE_PAGE}"
            )
        else:
            max_jp = "Jackpot amount unavailable this run"
            max_prov = f"Draw confirmed for {max_draw_date}. See {WCLC_MAX_PRIZE_PAGE}"
    elif previous_data and "lotto_max" in previous_data:
        max_win_nums = previous_data["lotto_max"]["winning_numbers"]
        max_bonus = previous_data["lotto_max"].get("bonus")
        max_draw_date = previous_data["lotto_max"].get("draw_date", "unknown")
        max_jp = previous_data["lotto_max"].get("jackpot", "Unavailable")
        max_prov = previous_data["lotto_max"].get("winner_province", "Unavailable")
    else:
        max_win_nums, max_bonus, max_draw_date = None, None, None
        max_jp, max_prov = "Unavailable", "Unavailable"

    # Lotto 6/49 데이터 구성
    if l649_result:
        l649_win_nums = l649_result["winning_numbers"]
        l649_bonus = l649_result["bonus"]
        l649_draw_date = l649_result["draw_date"]

        if home_jackpots:
            gb_amount = home_jackpots["gold_ball_jackpot"]
            gb_next_draw = home_jackpots["gold_ball_next_draw"]
        else:
            gb_amount = l649_result["next_gold_ball_jackpot"]
            gb_next_draw = "next draw"

        l649_gb_display = f"${gb_amount / 1_000_000:.0f} Million"
        outcome_text = (
            "Guaranteed $1,000,000 prize won (White ball drawn)."
            if l649_result["latest_ball_outcome"] == "White"
            else "GOLD BALL JACKPOT WON on this draw!"
        )
        l649_prov = (
            f"Draw confirmed for {l649_draw_date}. {outcome_text} "
            f"Next Gold Ball jackpot ({gb_next_draw}): {l649_gb_display}. "
            f"Winning ticket location: see official WCLC prize breakdown — {WCLC_649_PRIZE_PAGE}"
        )
    elif previous_data and "lotto_649" in previous_data:
        l649_win_nums = previous_data["lotto_649"]["winning_numbers"]
        l649_bonus = previous_data["lotto_649"].get("bonus")
        l649_draw_date = previous_data["lotto_649"].get("draw_date", "unknown")
        l649_gb_display = previous_data["lotto_649"].get("gold_ball", "Unavailable")
        l649_prov = previous_data["lotto_649"].get("winner_province", "Unavailable")
    else:
        l649_win_nums, l649_bonus, l649_draw_date = None, None, None
        l649_gb_display, l649_prov = "Unavailable", "Unavailable"

    home_display = {
        "date": today_date,
        "display_date": display_date,
        "lotto_max": {
            "jackpot": max_jp,
            "winner_province": max_prov,
            "winning_numbers": max_win_nums,
            "bonus": max_bonus,
            "draw_date": max_draw_date,
            "frequencies": max_frequencies,
            "frequency_source": max_freq_source,
            "frequency_draws_counted": max_draw_count,
        },
        "lotto_649": {
            "gold_ball": l649_gb_display,
            "winner_province": l649_prov,
            "winning_numbers": l649_win_nums,
            "bonus": l649_bonus,
            "draw_date": l649_draw_date,
            "frequencies": l649_frequencies,
            "frequency_source": l649_freq_source,
            "frequency_draws_counted": l649_draw_count,
        },
    }

    with open(display_path, "w", encoding="utf-8") as f:
        json.dump(home_display, f, indent=4, ensure_ascii=False)

    os.makedirs("posts", exist_ok=True)
    index_filename = "posts_index.json"

    posts_list = []
    if os.path.exists(index_filename):
        try:
            with open(index_filename, "r", encoding="utf-8") as f:
                posts_list = json.load(f)
        except Exception:
            posts_list = []

    new_post = None

    if weekday in [2, 5] and max_result:
        ai_nums = generate_ai_numbers(52, 7)
        note = build_deep_analysis_note("Lotto Max", max_draw_date, max_win_nums, ai_nums, max_jp, max_prov)
        new_post = {
            "id": f"max-{today_date}",
            "game": "Lotto Max",
            "date": today_date,
            "display_date": display_date,
            "draw_date": max_draw_date,
            "title": f"Lotto Max Official Draw Results & Analysis (Draw Date: {max_draw_date})",
            "summary": f"Verified results for the Lotto Max draw on {max_draw_date}. {max_prov}",
            "jackpot": max_jp,
            "winner_province": max_prov,
            "winning_numbers": max_win_nums,
            "bonus": max_bonus,
            "ai_recommended": ai_nums,
            "ai_note": note,
        }

    if weekday in [3, 6] and l649_result:
        ai_nums = generate_ai_numbers(49, 6)
        note = build_deep_analysis_note("Lotto 6/49", l649_draw_date, l649_win_nums, ai_nums, l649_gb_display, l649_prov)
        new_post = {
            "id": f"649-{today_date}",
            "game": "Lotto 6/49",
            "date": today_date,
            "display_date": display_date,
            "draw_date": l649_draw_date,
            "title": f"Lotto 6/49 Official Draw Results & Analysis (Draw Date: {l649_draw_date})",
            "summary": f"Verified results for the Lotto 6/49 draw on {l649_draw_date}. {l649_prov}",
            "jackpot": l649_gb_display,
            "winner_province": l649_prov,
            "winning_numbers": l649_win_nums,
            "bonus": l649_bonus,
            "ai_recommended": ai_nums,
            "ai_note": note,
        }

    if new_post:
        post_path = f"posts/{new_post['id']}.json"
        with open(post_path, "w", encoding="utf-8") as f:
            json.dump(new_post, f, indent=4, ensure_ascii=False)

        posts_list = [p for p in posts_list if p.get("id") != new_post["id"]]
        posts_list.insert(0, {
            "id": new_post["id"],
            "game": new_post["game"],
            "date": today_date,
            "display_date": display_date,
            "title": new_post["title"],
            "summary": new_post["summary"],
        })

    valid_posts = []
    for file_name in os.listdir("posts"):
        if file_name.endswith(".json"):
            p_id = file_name.replace(".json", "")
            try:
                with open(os.path.join("posts", file_name), "r", encoding="utf-8") as pf:
                    p_data = json.load(pf)
                    valid_posts.append({
                        "id": p_data.get("id", p_id),
                        "game": p_data.get("game", "Lotto"),
                        "date": p_data.get("date", ""),
                        "display_date": p_data.get("display_date", ""),
                        "title": p_data.get("title", ""),
                        "summary": p_data.get("summary", ""),
                    })
            except Exception:
                pass

    valid_posts.sort(key=lambda x: x.get("date", ""), reverse=True)

    with open(index_filename, "w", encoding="utf-8") as f:
        json.dump(valid_posts, f, indent=4, ensure_ascii=False)

    build_index_html(home_display, valid_posts)
    print(f"Build finished for {today_date}.")

if __name__ == "__main__":
    main()
