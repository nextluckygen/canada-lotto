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
WCLC_HOME_URL = "https://www.wclc.com/home.htm"

# 참고: WCLC "Prize Details" 버튼은 JS/AJAX로 열리는 팝업이라 정적 스크래핑으로
# 당첨 지역(province)을 안정적으로 가져올 방법이 없다. 이 스크립트는 지역명을
# 지어내지 않고, 대신 공식 페이지로 바로 연결되는 링크를 제공한다.
WCLC_MAX_PRIZE_PAGE = "https://www.wclc.com/winning-numbers/lotto-max-extra.htm"
WCLC_649_PRIZE_PAGE = "https://www.wclc.com/winning-numbers/lotto-649-extra.htm"

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DATE_PATTERN = r'((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+\w+\s+\d{1,2},\s+\d{4})'

# ==========================================
# 1. 빈도 데이터
#    - draw_history.json에 실제 회차 결과를 계속 누적하고, 6개월(HISTORY_WINDOW_DAYS)이
#      지난 회차는 자동으로 제거한 뒤 그 시점 기준으로 빈도를 "직접 계산"한다.
#    - 서비스 초기(누적 회차가 너무 적을 때)는 계산값이 통계적으로 의미가 없으므로,
#      MIN_DRAWS_FOR_LIVE_STATS 미만이면 아래 SEED_* 값(참고용 시드 스냅샷)을 대신 쓴다.
#      이 시드값은 실제 6개월 데이터가 쌓이면 자동으로 안 쓰이게 된다.
# ==========================================
HISTORY_FILE = "draw_history.json"
HISTORY_WINDOW_DAYS = 183  # 약 6개월
MIN_DRAWS_FOR_LIVE_STATS = 15  # 이 회차 수 미만이면 시드값 사용 (통계적으로 불안정하므로)

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
# 3b. draw_history.json 롤링 누적 관리
#     -> 이 파일이 "6개월 빈도표"의 실제 데이터 소스가 된다.
# ==========================================
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
            continue  # 형식이 깨진 과거 레코드는 버린다
        if (today_dt.date() - rec_dt.date()).days <= window_days:
            kept.append(rec)
    kept.sort(key=lambda r: parse_draw_date(r["date"]))
    return kept


def add_draw_to_history(history, game_key, draw_date_str, numbers, bonus, today_dt):
    """오늘 새로 검증된 회차를 히스토리에 추가(같은 날짜가 이미 있으면 덮어쓰기)하고,
    6개월이 지난 회차는 정리한다."""
    records = history.get(game_key, [])
    records = [r for r in records if r.get("date") != draw_date_str]
    records.append({"date": draw_date_str, "numbers": numbers, "bonus": bonus})
    history[game_key] = prune_history(records, today_dt)
    return history


def compute_frequencies_from_history(records, total_numbers, include_bonus=False):
    """records: [{"date":..., "numbers":[...], "bonus":...}, ...] -> {"1": count, ...}"""
    counts = {str(n): 0 for n in range(1, total_numbers + 1)}
    for rec in records:
        for n in rec.get("numbers", []):
            key = str(n)
            if key in counts:
                counts[key] += 1
        if include_bonus and rec.get("bonus") is not None:
            key = str(rec["bonus"])
            if key in counts:
                counts[key] += 1
    return counts


def resolve_frequencies(history_records, total_numbers, seed_frequencies):
    """실제 누적 회차가 충분하면 계산값을, 부족하면 시드값을 사용한다.
    두 경우 모두 어떤 값을 썼는지 함께 반환해 로그/디버깅에 활용한다."""
    if len(history_records) >= MIN_DRAWS_FOR_LIVE_STATS:
        return compute_frequencies_from_history(history_records, total_numbers), "live", len(history_records)
    return dict(seed_frequencies), "seed", len(history_records)


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
    # 참고: 페이지에 보이는 최근 회차가 전부 White였다면(=최근 골드볼 당첨이 없었다면)
    # white_streak은 그냥 "스크래핑 창 안에서 관찰된 연속 White 횟수"가 된다.
    # 실제 골드볼 잭팟 실수령액은 main()에서 WCLC 홈페이지 실시간 티커
    # (fetch_home_jackpots)를 우선 사용하고, 이 값은 그게 실패했을 때만 쓰는
    # 2차 추정값이므로 여기서 에러로 전체 회차 파싱을 막을 필요가 없다.
    # (이전엔 여기서 무조건 raise해서, 잭팟이 여러 회 계속 이월될 때마다
    #  6/49 포스팅 전체가 막히는 버그가 있었다.)

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


# ==========================================
# 5a. 히스토리 누적용: 페이지에 보이는 "모든" 회차를 관대하게 파싱
#     (메인 표시용 parse_649/parse_max는 최신 1개 회차만 엄격하게 검증하지만,
#      이 함수들은 draw_history.json을 채우기 위해 여러 회차를 최대한 수집한다.
#      개별 회차가 이상하면 그 회차만 건너뛰고 나머지는 계속 수집한다.)
# ==========================================
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


# ==========================================
# 5b. WCLC 홈페이지 실시간 잭팟 티커 파싱
#     (Prize Breakdown/당첨 지역은 JS 팝업이라 스크래핑 불가 -> 시도하지 않음.
#      대신 공식적으로 발표된 "다음 회차 잭팟 금액"만 안전하게 가져온다.)
# ==========================================
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
    if not (1 <= balls_remaining <= 26):
        raise ScrapeError(f"Home: implausible Balls Remaining value: {balls_remaining}")

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
    # 공식 규칙: MaxPlus 상품 개수 = 잭팟 금액(백만 단위). 어긋나면 페이지 구조가
    # 바뀐 것으로 간주하고 신뢰하지 않는다.
    if maxplus_count != max_millions:
        raise ScrapeError(
            f"Home: MaxPlus count ({maxplus_count}) does not match jackpot millions "
            f"({max_millions}) — page structure may have changed"
        )
    if not (10 <= max_millions <= 90):
        raise ScrapeError(f"Home: implausible Lotto Max jackpot value: ${max_millions}M")

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

    # ---- draw_history.json 갱신 (6개월 롤링 빈도표의 실제 데이터 소스) ----
    # 페이지에 보이는 "모든" 회차(각 게임당 최근 8~10회차)를 매번 훑어서 누적한다.
    # 최신 1회차만 넣으면 서비스 초반 몇 달은 데이터가 거의 없어 시드값에 계속
    # 의존하게 되므로, 이미 그 페이지에 실려있는 실제 과거 회차도 함께 백필한다.
    # (날짜 기준 중복 제거되므로 여러 번 실행해도 안전하다.)
    history = load_history()
    if max_result:
        try:
            for draw in parse_max_all(max_text, today_dt):
                history = add_draw_to_history(
                    history, "lotto_max", draw["draw_date"],
                    draw["winning_numbers"], draw["bonus"], today_dt,
                )
        except Exception as e:
            print(f"[WARN] Max history backfill parse failed (non-fatal): {e}", file=sys.stderr)
    if l649_result:
        try:
            for draw in parse_649_all(l649_text, today_dt):
                history = add_draw_to_history(
                    history, "lotto_649", draw["draw_date"],
                    draw["winning_numbers"], draw["bonus"], today_dt,
                )
        except Exception as e:
            print(f"[WARN] 649 history backfill parse failed (non-fatal): {e}", file=sys.stderr)
    # 스크래핑 실패 여부와 무관하게, 이미 저장된 회차 중 6개월 지난 것은 정리한다.
    history["lotto_max"] = prune_history(history.get("lotto_max", []), today_dt)
    history["lotto_649"] = prune_history(history.get("lotto_649", []), today_dt)
    save_history(history)

    max_frequencies, max_freq_source, max_draw_count = resolve_frequencies(
        history["lotto_max"], 52, SEED_MAX_FREQUENCIES
    )
    l649_frequencies, l649_freq_source, l649_draw_count = resolve_frequencies(
        history["lotto_649"], 49, SEED_649_FREQUENCIES
    )
    print(
        f"[INFO] Frequency source — Max: {max_freq_source} ({max_draw_count} draws in window), "
        f"6/49: {l649_freq_source} ({l649_draw_count} draws in window)"
    )

    try:
        home_text = fetch_text(WCLC_HOME_URL)
        home_jackpots = fetch_home_jackpots(home_text, today_dt)
        # 교차검증: 히스토리 기반 계산값과 홈페이지 실시간 값이 다르면 로그만 남기고
        # 홈페이지의 "공식 발표 값"을 최종 소스로 신뢰한다 (계산값은 검증용 보조 지표).
        if l649_result and l649_result["next_gold_ball_jackpot"] != home_jackpots["gold_ball_jackpot"]:
            print(
                f"[WARN] Gold Ball jackpot mismatch: computed="
                f"{l649_result['next_gold_ball_jackpot']} vs live={home_jackpots['gold_ball_jackpot']}. "
                f"Using live value.",
                file=sys.stderr,
            )
    except Exception as e:
        home_error = str(e)
        print(f"[WARN] WCLC home jackpot ticker scrape/validation failed: {home_error}", file=sys.stderr)

    # ---- Lotto Max 데이터 구성 ----
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
            # 잭팟 티커 스크래핑이 실패한 경우: 금액을 지어내지 않는다.
            max_jp = "Jackpot amount unavailable this run — see official WCLC site"
            max_prov = (
                f"Draw confirmed for {max_draw_date}. Jackpot/winner details unavailable this run "
                f"({home_error}). See {WCLC_MAX_PRIZE_PAGE}"
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

        # 홈페이지 실시간 값을 최우선으로 신뢰하고, 실패 시에만 계산값으로 대체
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

    build_index_html(home_display, valid_posts)

    print(f"Build finished for {today_date}.")
    print(f"  Max: {'OK' if max_result else 'FALLBACK/UNAVAILABLE - ' + str(max_error)}")
    print(f"  649: {'OK' if l649_result else 'FALLBACK/UNAVAILABLE - ' + str(l649_error)}")

    # 두 게임 모두 이번 실행에서 검증 실패했다면 CI를 실패로 표시해서
    # 사람이 반드시 확인하게 만든다 (조용히 넘어가지 않는다).
    if max_error and l649_error:
        print("[FATAL] Both games failed scrape/validation this run.", file=sys.stderr)
        sys.exit(1)


# ==========================================
# 6. index.html 빌드타임 렌더링
#    - AdSense가 "Google-served ads on screens without publisher-content"로
#      반려한 핵심 원인: 홈페이지 핵심 콘텐츠가 클라이언트 JS의 비동기 fetch가
#      끝나야 채워지는 구조라, 크롤러가 그 fetch 완료 전에 스냅샷을 찍으면
#      "Loading..." 같은 빈 화면이 캡처될 수 있었다.
#    - 해결책: 매 실행마다 실제 데이터를 index.html에 직접 구워 넣는다.
#      JS 색상 로직(Hot/Mid/Cold 임계값)을 Python으로 1:1 동일하게 재구현해서
#      서버 렌더링 결과와 클라이언트 JS 재렌더링 결과가 항상 일치하게 만든다.
# ==========================================
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
    """<tag id="element_id" ...>OLD</tag> 의 OLD 부분만 교체한다."""
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

    # 기본 활성 탭은 Lotto Max
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

    # 클라이언트 JS가 fetch 없이 바로 쓸 수 있도록 실제 데이터를 그대로 심어둔다.
    # (초기 화면 콘텐츠는 이미 위에서 정적으로 완성됐고, 이건 탭 전환/번호 생성
    #  같은 상호작용 기능이 fetch 경쟁 상태 없이 즉시 동작하게 하기 위함이다.)
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
        print(f"[WARN] {TEMPLATE_PATH} not found — skipping index.html rebuild (existing index.html left untouched).", file=sys.stderr)
        return
    try:
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            template_html = f.read()
        rendered = render_index_html(template_html, home_display, posts_list)
        with open(INDEX_OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(rendered)
        print("[INFO] index.html rebuilt with real data baked in (no client-fetch dependency for initial content).")
    except Exception as e:
        print(f"[WARN] index.html rebuild failed (existing index.html left untouched): {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
