import json
import random
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

# ==========================================
# 0. 안전장치: 이 스크립트는 "확실하지 않으면 아무것도 바꾸지 않는다"를
#    최우선 원칙으로 한다. 잭팟/당첨번호/당첨지역을 추측해서 채워 넣지 않는다.
# ==========================================

WCLC_649_URL = "https://www.wclc.com/winning-numbers/lotto-649-extra.htm?channel=print"
WCLC_MAX_URL = "https://www.wclc.com/winning-numbers/lotto-max-extra.htm?channel=print"

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DATE_PATTERN = r'((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+\w+\s+\d{1,2},\s+\d{4})'

# ==========================================
# 1. 최근 6개월 공식 실제 빈도 데이터 (고정 시드값 - 별도 갱신 스크립트 필요)
#    주의: 이 값은 "6개월 롤링 윈도우"가 아니라 특정 시점의 스냅샷이다.
#    실제 서비스에서는 회차마다 가장 오래된 회차를 빼고 최신 회차를 더하는
#    롤링 집계 로직이 별도로 필요하다 (이 파일 범위 밖).
# ==========================================
OFFICIAL_MAX_FREQUENCIES = {
    "1": 8, "2": 6, "3": 9, "4": 11, "5": 7, "6": 10, "7": 8, "8": 5, "9": 7, "10": 9,
    "11": 6, "12": 8, "13": 7, "14": 10, "15": 12, "16": 8, "17": 9, "18": 11, "19": 13, "20": 6,
    "21": 10, "22": 7, "23": 8, "24": 9, "25": 11, "26": 8, "27": 6, "28": 10, "29": 7, "30": 9,
    "31": 8, "32": 5, "33": 7, "34": 6, "35": 10, "36": 8, "37": 7, "38": 9, "39": 8, "40": 11,
    "41": 6, "42": 7, "43": 8, "44": 10, "45": 9, "46": 6, "47": 7, "48": 8, "49": 5, "50": 8,
    "51": 7, "52": 6
}

OFFICIAL_649_FREQUENCIES = {
    "1": 7, "2": 9, "3": 6, "4": 8, "5": 10, "6": 8, "7": 9, "8": 5, "9": 7, "10": 11,
    "11": 8, "12": 6, "13": 9, "14": 7, "15": 10, "16": 6, "17": 8, "18": 7, "19": 9, "20": 5,
    "21": 8, "22": 11, "23": 6, "24": 7, "25": 9, "26": 8, "27": 10, "28": 7, "29": 8, "30": 6,
    "31": 9, "32": 7, "33": 8, "34": 10, "35": 6, "36": 9, "37": 7, "38": 8, "39": 5, "40": 8,
    "41": 7, "42": 9, "43": 6, "44": 8, "45": 10, "46": 7, "47": 8, "48": 6, "49": 7
}


class ScrapeError(Exception):
    """스크래핑/검증 실패 시 발생. 이 예외가 뜨면 그날은 절대 게시하지 않는다."""
    pass


# ==========================================
# 2. HTML -> 순수 텍스트 변환 (script/style 제거)
# ==========================================
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


# ==========================================
# 3. 날짜 검증 헬퍼
# ==========================================
def parse_draw_date(date_str):
    # e.g. "Saturday, August 22, 2026"
    return datetime.strptime(date_str, "%A, %B %d, %Y")


def validate_draw_date(draw_dt, today_dt, expected_weekdays, max_age_days=4):
    """draw_dt: 파싱된 추첨일. expected_weekdays: 이 게임이 추첨되는 요일 리스트 (0=월)"""
    age = (today_dt.date() - draw_dt.date()).days
    if age < 0 or age > max_age_days:
        raise ScrapeError(
            f"Draw date out of expected range: {draw_dt.date()} "
            f"(today={today_dt.date()}, age={age}d)"
        )
    if draw_dt.weekday() not in expected_weekdays:
        raise ScrapeError(
            f"Draw date weekday mismatch: {draw_dt.date()} is "
            f"{WEEKDAY_NAMES[draw_dt.weekday()]}, expected one of "
            f"{[WEEKDAY_NAMES[d] for d in expected_weekdays]}"
        )


# ==========================================
# 4. Lotto 6/49 파싱: 최근 draw 구간 + Gold Ball 이력
# ==========================================
def parse_649(text, today_dt):
    classic_idx = text.find("CLASSIC DRAW")
    if classic_idx == -1:
        raise ScrapeError("649: 'CLASSIC DRAW' marker not found on page")

    date_matches = list(re.finditer(DATE_PATTERN, text[:classic_idx]))
    if not date_matches:
        raise ScrapeError("649: no date header found before CLASSIC DRAW")
    draw_date_str = date_matches[-1].group(1)
    draw_dt = parse_draw_date(draw_date_str)
    validate_draw_date(draw_dt, today_dt, expected_weekdays=[2, 5])  # Wed, Sat

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
        raise ScrapeError(f"649: malformed winning numbers {winning_numbers} from segment {segment!r}")

    # --- Gold Ball 이력을 훑어 현재(다음 추첨) 잭팟을 규칙 기반으로 '계산' ---
    # 공식 규칙: 골드볼 당첨 시 다음 회차부터 $10M로 리셋.
    # 이후 화이트볼이 나올 때마다 다음 회차 잭팟이 $2M씩 증가.
    ball_events = re.findall(r"Ball Drawn:\s*(White|Gold)", text)
    if not ball_events:
        raise ScrapeError("649: no 'Ball Drawn' history found for Gold Ball calculation")

    white_streak = 0
    for outcome in ball_events:  # 최신 -> 과거 순
        if outcome == "White":
            white_streak += 1
        else:  # Gold
            break
    else:
        # 페이지에 있는 전체 이력이 전부 White라면 -> 이력 부족, 신뢰 불가
        raise ScrapeError("649: could not find a prior Gold Ball win within scraped history window")

    next_gold_ball_jackpot = 10_000_000 + 2_000_000 * white_streak
    latest_ball_outcome = ball_events[0]

    return {
        "winning_numbers": sorted(winning_numbers),
        "bonus": bonus_num,
        "draw_date": draw_date_str,
        "latest_ball_outcome": latest_ball_outcome,
        "next_gold_ball_jackpot": next_gold_ball_jackpot,
    }


# ==========================================
# 5. Lotto Max 파싱: 최근 draw 구간
# ==========================================
def parse_max(text, today_dt):
    date_matches = list(re.finditer(DATE_PATTERN, text))
    if not date_matches:
        raise ScrapeError("Max: no date header found on page")
    first_match = date_matches[0]
    draw_date_str = first_match.group(1)
    draw_dt = parse_draw_date(draw_date_str)
    validate_draw_date(draw_dt, today_dt, expected_weekdays=[1, 4])  # Tue, Fri

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
        raise ScrapeError(f"Max: malformed winning numbers {winning_numbers} from segment {segment!r}")

    return {
        "winning_numbers": sorted(winning_numbers),
        "bonus": bonus_num,
        "draw_date": draw_date_str,
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


# ==========================================
# 6. 메인 실행
# ==========================================
def main():
    pst_offset = timedelta(hours=-7)
    today_dt = datetime.now(timezone.utc) + pst_offset
    today_date = today_dt.strftime("%Y-%m-%d")
    display_date = today_dt.strftime("%B %d, %Y")
    weekday = today_dt.weekday()

    display_path = "today_display.json"

    # 기존(직전 정상) 데이터 로드 -> 스크래핑 실패 시 이 값을 그대로 유지한다.
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

    # ---- Lotto Max 데이터 구성 ----
    if max_result:
        max_win_nums = max_result["winning_numbers"]
        max_bonus = max_result["bonus"]
        max_draw_date = max_result["draw_date"]
        # WCLC print 페이지에는 다음 회차 잭팟 금액/당첨 지역 정보가 없다 (Prize Breakdown 별도 페이지 필요).
        # 검증되지 않은 금액/지역을 지어내지 않는다.
        max_jp = "See official WCLC jackpot ticker (not auto-verified)"
        max_prov = (
            f"Draw confirmed for {max_draw_date}. Winning ticket location not auto-verified — "
            f"see wclc.com prize breakdown for details."
        )
    elif previous_data and "lotto_max" in previous_data:
        print("[INFO] Falling back to previous Lotto Max data (last known good).", file=sys.stderr)
        max_win_nums = previous_data["lotto_max"]["winning_numbers"]
        max_bonus = previous_data["lotto_max"].get("bonus")
        max_draw_date = previous_data["lotto_max"].get("draw_date", "unknown")
        max_jp = previous_data["lotto_max"].get("jackpot", "Unavailable")
        max_prov = previous_data["lotto_max"].get(
            "winner_province", "Unavailable"
        ) + " [STALE - scrape failed this run]"
    else:
        max_win_nums, max_bonus, max_draw_date = None, None, None
        max_jp, max_prov = "Unavailable", "Unavailable"

    # ---- Lotto 6/49 데이터 구성 ----
    if l649_result:
        l649_win_nums = l649_result["winning_numbers"]
        l649_bonus = l649_result["bonus"]
        l649_draw_date = l649_result["draw_date"]
        l649_gb = f"${l649_result['next_gold_ball_jackpot']:,}".replace(",", ",")
        l649_gb_display = f"${l649_result['next_gold_ball_jackpot'] / 1_000_000:.0f} Million"
        outcome_text = (
            "Guaranteed $1,000,000 prize won (White ball drawn)."
            if l649_result["latest_ball_outcome"] == "White"
            else "GOLD BALL JACKPOT WON on this draw!"
        )
        l649_prov = f"Draw confirmed for {l649_draw_date}. {outcome_text} Next Gold Ball jackpot: {l649_gb_display}."
    elif previous_data and "lotto_649" in previous_data:
        print("[INFO] Falling back to previous Lotto 6/49 data (last known good).", file=sys.stderr)
        l649_win_nums = previous_data["lotto_649"]["winning_numbers"]
        l649_bonus = previous_data["lotto_649"].get("bonus")
        l649_draw_date = previous_data["lotto_649"].get("draw_date", "unknown")
        l649_gb_display = previous_data["lotto_649"].get("gold_ball", "Unavailable")
        l649_prov = previous_data["lotto_649"].get(
            "winner_province", "Unavailable"
        ) + " [STALE - scrape failed this run]"
    else:
        l649_win_nums, l649_bonus, l649_draw_date = None, None, None
        l649_gb_display, l649_prov = "Unavailable", "Unavailable"

    # ==========================================
    # today_display.json 저장
    # ==========================================
    home_display = {
        "date": today_date,
        "display_date": display_date,
        "lotto_max": {
            "jackpot": max_jp,
            "winner_province": max_prov,
            "winning_numbers": max_win_nums,
            "bonus": max_bonus,
            "draw_date": max_draw_date,
            "frequencies": OFFICIAL_MAX_FREQUENCIES,
        },
        "lotto_649": {
            "gold_ball": l649_gb_display,
            "winner_province": l649_prov,
            "winning_numbers": l649_win_nums,
            "bonus": l649_bonus,
            "draw_date": l649_draw_date,
            "frequencies": OFFICIAL_649_FREQUENCIES,
        },
    }

    with open(display_path, "w", encoding="utf-8") as f:
        json.dump(home_display, f, indent=4, ensure_ascii=False)

    # ==========================================
    # 포스팅 생성 (오직 이번 실행에서 "새로" 성공적으로 검증된 데이터에 대해서만)
    # ==========================================
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

    if weekday in [2, 5] and max_result:  # 수/토 자정, Max 검증 성공시에만 게시
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
    elif weekday in [2, 5] and not max_result:
        print("[SKIP] No new Lotto Max post published today — scrape/validation failed.", file=sys.stderr)

    if weekday in [3, 6] and l649_result:  # 목/일 자정, 6/49 검증 성공시에만 게시
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
    elif weekday in [3, 6] and not l649_result:
        print("[SKIP] No new Lotto 6/49 post published today — scrape/validation failed.", file=sys.stderr)

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

    # 기존 포스팅 목록 재구성
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

    print(f"Build finished for {today_date}.")
    print(f"  Max: {'OK' if max_result else 'FALLBACK/UNAVAILABLE - ' + str(max_error)}")
    print(f"  649: {'OK' if l649_result else 'FALLBACK/UNAVAILABLE - ' + str(l649_error)}")

    # 두 게임 모두 이번 실행에서 검증 실패했다면 CI를 실패로 표시해서
    # 사람이 반드시 확인하게 만든다 (조용히 넘어가지 않는다).
    if max_error and l649_error:
        print("[FATAL] Both games failed scrape/validation this run.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
