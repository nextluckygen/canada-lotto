import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from html.parser import HTMLParser

import build  # 정적 사이트 렌더러 (build.py)

# ==========================================
# 0. 안전장치: 이 스크립트는 "확실하지 않으면 아무것도 바꾸지 않는다"를
#    최우선 원칙으로 한다. 잭팟/당첨번호를 추측해서 채워 넣지 않는다.
#
# 2026-10 구조 변경 (AdSense "Low value content" 대응):
#   - 회차마다 새 posts/*.html 페이지를 만들던 기능을 완전히 중단했다.
#     (같은 틀에 숫자만 바뀌는 페이지 = thin / auto-generated content)
#   - 대신 매일 실행 시 draw_history.json(전체 회차 누적)을 갱신하고,
#     build.py가 홈페이지 + 게임별 결과 아카이브 페이지 2개
#     (lotto-max-results.html, lotto-649-results.html)를 다시 만든다.
#   - 추천 번호/셔플 번호 생성기는 제거했다. 이 사이트는 예측 서비스가 아니다.
#
# 사용법:
#   python main.py              # WCLC에서 결과를 가져와 히스토리 갱신 후 사이트 빌드
#   python main.py --build-only # 네트워크 없이 기존 draw_history.json으로 사이트만 빌드
# ==========================================

WCLC_649_URL = "https://www.wclc.com/winning-numbers/lotto-649-extra.htm?channel=print"
WCLC_MAX_URL = "https://www.wclc.com/winning-numbers/lotto-max-extra.htm?channel=print"
WCLC_HOME_URL = "https://www.wclc.com/home.htm"

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DATE_PATTERN = r'((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+\w+\s+\d{1,2},\s+\d{4})'

HISTORY_FILE = "draw_history.json"

# 회차별 게시물 생성 기능은 폐기됨 (thin content). True로 바꿔도 게시물은 만들지 않는다.
GENERATE_POSTS = False


class ScrapeError(Exception):
    """스크래핑/검증 실패 시 발생. 이 예외가 뜨면 그 게임의 데이터는 갱신하지 않는다."""
    pass


# ==========================================
# 1. HTML -> 순수 텍스트 변환 (script/style 제거)
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
# 2. 날짜 헬퍼
# ==========================================
def parse_draw_date(date_str):
    # e.g. "Saturday, August 22, 2026" 또는 "Saturday, August 2, 2026"
    return datetime.strptime(date_str, "%A, %B %d, %Y")


def iso_date(date_str):
    return parse_draw_date(date_str).strftime("%Y-%m-%d")


def validate_draw_date(draw_dt, today_dt, expected_weekdays, max_age_days=7):
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
# 3. draw_history.json 관리 — 전체 회차를 계속 누적한다 (더 이상 6개월 롤링 삭제 안 함).
#    구조:
#    {
#      "lotto_max": [{"date": "Friday, October 02, 2026", "numbers": [...], "bonus": 26,
#                     "jackpot": 75000000?, "maxmillions": 12?, "maxplus": 75?}, ...],
#      "lotto_649": [{"date": ..., "numbers": [...], "bonus": ..,
#                     "gold_ball": {"ball": "White"|"Gold", "prize": 1000000}?,
#                     "gold_ball_jackpot": 18000000?}, ...],
#      "upcoming": {"lotto_max": {...}, "lotto_649": {...}},  # WCLC 잭팟 티커(다음 회차)
#      "meta": {"last_checked": "2026-10-07T00:05-07:00", "backfill": {...}}
#    }
#    2026-10: Lotto 6/49 1982~, Lotto Max 2009~ 전체 회차를 백필했다 (tools/backfill_merge.py).
#    Lotto Max는 번호 범위가 1-49 (2009-2019) -> 1-50 (2019-05-14~) -> 1-52 (2026-04-14~)로
#    바뀌었으므로 통계는 build.py에서 기간(era)별로 따로 계산한다.
# ==========================================
def load_history():
    data = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data.setdefault("lotto_max", [])
    data.setdefault("lotto_649", [])
    data.setdefault("upcoming", {})
    data.setdefault("meta", {})
    return data


def save_history(history):
    """전체 히스토리(1982년~)가 커졌으므로 회차 1건을 한 줄로 저장한다 (여전히 유효한 JSON)."""
    chunks = []
    for key, value in history.items():
        if isinstance(value, list):
            body = ",\n".join("    " + json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in value)
            chunks.append(f"  {json.dumps(key)}: [\n{body}\n  ]")
        else:
            chunks.append(f"  {json.dumps(key)}: " + json.dumps(value, ensure_ascii=False, indent=2).replace("\n", "\n  "))
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        f.write("{\n" + ",\n".join(chunks) + "\n}\n")


def normalize_records(records):
    """형식이 깨진 레코드 제거 + 날짜 기준 중복 제거 + 날짜순 정렬."""
    by_date = {}
    for rec in records:
        try:
            key = iso_date(rec["date"])
        except Exception:
            continue
        # 같은 날짜가 여러 번 있으면 나중 값(=더 최근 스크래핑)이 이긴다
        by_date[key] = rec
    return [by_date[k] for k in sorted(by_date)]


def upsert_draw(history, game_key, draw):
    """새로 검증된 회차를 히스토리에 추가/갱신한다. 기존 레코드의 부가정보
    (잭팟, 골드볼 결과 등)는 새 값이 없을 때 그대로 유지한다."""
    records = history.get(game_key, [])
    target = iso_date(draw["date"])
    existing = None
    for rec in records:
        try:
            if iso_date(rec["date"]) == target:
                existing = rec
                break
        except Exception:
            continue
    if existing is None:
        existing = {"date": draw["date"]}
        records.append(existing)
    existing["date"] = draw["date"]
    existing["numbers"] = draw["numbers"]
    existing["bonus"] = draw["bonus"]
    if draw.get("gold_ball"):
        existing["gold_ball"] = draw["gold_ball"]

    # 이전 실행에서 저장해둔 "다음 회차 잭팟 티커"가 이 회차 날짜와 같으면 붙여준다.
    upcoming = (history.get("upcoming") or {}).get(game_key) or {}
    if upcoming.get("date") == target:
        if game_key == "lotto_max":
            for k in ("jackpot", "maxmillions", "maxplus"):
                if upcoming.get(k) is not None:
                    existing.setdefault(k, upcoming[k])
        else:
            if upcoming.get("gold_ball_jackpot") is not None:
                existing.setdefault("gold_ball_jackpot", upcoming["gold_ball_jackpot"])

    history[game_key] = normalize_records(records)
    return history


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
#     개별 회차가 이상하면 그 회차만 건너뛴다.
# ==========================================
def parse_649_all(text, today_dt):
    results = []
    classic_positions = [m.start() for m in re.finditer("CLASSIC DRAW", text)]

    for idx, classic_idx in enumerate(classic_positions):
        block_end = classic_positions[idx + 1] if idx + 1 < len(classic_positions) else len(text)
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

        gold_idx = text.find("GOLD BALL DRAW", classic_idx, block_end)
        segment_end = gold_idx if gold_idx != -1 else min(classic_idx + 400, block_end)
        segment = text[classic_idx:segment_end]

        bonus_match = re.search(r"Bonus\s*(\d{1,2})", segment)
        if not bonus_match:
            continue
        bonus_num = int(bonus_match.group(1))

        segment_wo_bonus = re.sub(r"Bonus\s*\d{1,2}.*", "", segment)
        nums = [int(n) for n in re.findall(r"\b(\d{1,2})\b", segment_wo_bonus) if 1 <= int(n) <= 49]
        winning_numbers = nums[:6]
        if len(winning_numbers) != 6 or len(set(winning_numbers)) != 6:
            continue

        gold_ball = None
        if gold_idx != -1:
            gold_seg = text[gold_idx:block_end]
            ball_m = re.search(r"Ball Drawn:\s*(White|Gold)", gold_seg)
            prize_m = re.search(r"\$\s*([\d,]+)(?:\.\d{2})?\s*Ball Drawn", gold_seg)
            if ball_m:
                gold_ball = {"ball": ball_m.group(1)}
                if prize_m:
                    gold_ball["prize"] = int(prize_m.group(1).replace(",", ""))

        results.append({
            "date": draw_date_str,
            "numbers": sorted(winning_numbers),
            "bonus": bonus_num,
            "gold_ball": gold_ball,
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
            "date": draw_date_str,
            "numbers": sorted(winning_numbers),
            "bonus": bonus_num,
        })
    return results


# ==========================================
# 5b. WCLC 홈페이지 잭팟 티커 파싱 (다음 회차 잭팟만 가져온다)
# ==========================================
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
    if not (1 <= balls_remaining <= 30):
        raise ScrapeError(f"Home: implausible Balls Remaining value: {balls_remaining}")

    # 잭팟 금액과 날짜 사이에 다른 문구(MaxPlus "N x $100,000", 그리고 잭팟이
    # $50M을 넘으면 붙는 MaxMillions "N x $1 Million Prize" 등)가 껴 있을 수
    # 있고 그 구성이 계속 바뀌어왔다. 그래서 "$ N Million" 바로 뒤에 정확히
    # 무엇이 오는지는 요구하지 않고, 그 다음에 나오는 첫 날짜까지를 통째로
    # 잡은 뒤 그 안에서 MaxPlus 개수만 있으면 찾아 쓴다. 금액/날짜 자체를
    # 못 찾으면 여전히 ScrapeError를 내고 절대 숫자를 지어내지 않는다.
    max_pattern = re.compile(
                r"\$\s*([1-9]\d)\s*Million\b(.{0,240}?)" + date_re,
        re.DOTALL,
    )
    max_match = max_pattern.search(text, gb_match.end())
    if not max_match:
        raise ScrapeError("Home: Lotto Max jackpot ticker block not found")

    max_millions = int(max_match.group(1))
    between_text = max_match.group(2)
    max_next_date_str = max_match.group(3)
    maxplus_search = re.search(r"(\d+)\s*x\s*\$100,000", between_text)
    maxplus_count = int(maxplus_search.group(1)) if maxplus_search else None
    maxmillions_search = re.search(r"(\d+)\s*x\s*\$\s*1\s*Million", between_text)
    maxmillions_count = int(maxmillions_search.group(1)) if maxmillions_search else 0
    max_next_dt = parse_draw_date(max_next_date_str)

    if max_next_dt.date() < today_dt.date():
        raise ScrapeError(f"Home: Lotto Max next draw date {max_next_dt.date()} is in the past")
    if max_next_dt.weekday() not in (1, 4):
        raise ScrapeError(f"Home: Lotto Max next draw date {max_next_dt.date()} is not Tue/Fri")
    if maxplus_count is not None and maxplus_count != max_millions:
        print(
            f"[WARN] MaxPlus count ({maxplus_count}) != jackpot millions ({max_millions}); "
            "keeping the $N Million ticker anyway.",
            file=sys.stderr,
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
        "max_maxmillions_count": maxmillions_count,
    }


# ==========================================
# 6. 메인 실행
# ==========================================
def scrape_and_update(history, today_dt):
    """WCLC에서 결과/잭팟 티커를 가져와 history를 갱신한다. (max_error, l649_error) 반환."""
    max_error = l649_error = None

    try:
        max_text = fetch_text(WCLC_MAX_URL)
        latest = parse_max(max_text, today_dt)  # 최신 회차는 엄격하게 검증
        draws = parse_max_all(max_text, today_dt)
        if not any(iso_date(d["date"]) == iso_date(latest["draw_date"]) for d in draws):
            draws.append({"date": latest["draw_date"], "numbers": latest["winning_numbers"], "bonus": latest["bonus"]})
        for d in draws:
            upsert_draw(history, "lotto_max", d)
        print(f"[INFO] Lotto Max OK — latest {latest['draw_date']}, {len(draws)} draws seen on page")
    except Exception as e:
        max_error = str(e)
        print(f"[WARN] Lotto Max scrape/validation failed: {max_error}", file=sys.stderr)

    try:
        l649_text = fetch_text(WCLC_649_URL)
        latest = parse_649(l649_text, today_dt)
        draws = parse_649_all(l649_text, today_dt)
        if not any(iso_date(d["date"]) == iso_date(latest["draw_date"]) for d in draws):
            draws.append({"date": latest["draw_date"], "numbers": latest["winning_numbers"], "bonus": latest["bonus"],
                          "gold_ball": {"ball": latest["latest_ball_outcome"]}})
        for d in draws:
            upsert_draw(history, "lotto_649", d)
        print(f"[INFO] Lotto 6/49 OK — latest {latest['draw_date']}, {len(draws)} draws seen on page")
    except Exception as e:
        l649_error = str(e)
        print(f"[WARN] Lotto 6/49 scrape/validation failed: {l649_error}", file=sys.stderr)

    # 다음 회차 잭팟 티커 (실패해도 결과 데이터에는 영향 없음 — 금액을 지어내지 않는다)
    try:
        home_text = fetch_text(WCLC_HOME_URL)
        jp = fetch_home_jackpots(home_text, today_dt)
        history["upcoming"] = {
            "lotto_max": {
                "date": iso_date(jp["max_next_draw"]),
                "jackpot": jp["max_jackpot"],
                "maxmillions": jp.get("max_maxmillions_count") or 0,
                "maxplus": jp.get("max_maxplus_count"),
                "fetched": today_dt.strftime("%Y-%m-%d"),
            },
            "lotto_649": {
                "date": iso_date(jp["gold_ball_next_draw"]),
                "gold_ball_jackpot": jp["gold_ball_jackpot"],
                "balls_remaining": jp["gold_ball_balls_remaining"],
                "fetched": today_dt.strftime("%Y-%m-%d"),
            },
        }
        print(f"[INFO] Jackpot ticker OK — Max {jp['max_next_draw']}: ${jp['max_jackpot']:,}; "
              f"Gold Ball {jp['gold_ball_next_draw']}: ${jp['gold_ball_jackpot']:,}")
    except Exception as e:
        print(f"[WARN] WCLC jackpot ticker scrape/validation failed (non-fatal): {e}", file=sys.stderr)

    return max_error, l649_error


def main():
    build_only = "--build-only" in sys.argv
    # America/Vancouver는 PST/PDT를 자동으로 처리한다.
    today_dt = datetime.now(ZoneInfo("America/Vancouver"))

    if GENERATE_POSTS:
        print("[INFO] GENERATE_POSTS is ignored: per-draw posts were retired in Oct 2026.", file=sys.stderr)

    history = load_history()
    max_error = l649_error = None
    if not build_only:
        max_error, l649_error = scrape_and_update(history, today_dt)
        if not (max_error and l649_error):
            history["meta"]["last_checked"] = today_dt.isoformat(timespec="minutes")
    history["lotto_max"] = normalize_records(history["lotto_max"])
    history["lotto_649"] = normalize_records(history["lotto_649"])
    save_history(history)

    build.build_site(history, today_dt)

    print(f"Build finished for {today_dt.strftime('%Y-%m-%d')} (build_only={build_only}).")
    if not build_only:
        print(f"  Max: {'OK' if not max_error else 'FAILED - ' + str(max_error)}")
        print(f"  649: {'OK' if not l649_error else 'FAILED - ' + str(l649_error)}")
        # 두 게임 모두 실패하면 CI를 실패로 표시해서 사람이 확인하게 한다.
        if max_error and l649_error:
            print("[FATAL] Both games failed scrape/validation this run.", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
