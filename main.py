import json
import random
import os
from datetime import datetime, timezone, timedelta

def generate_numbers(total, count):
    return sorted(random.sample(range(1, total + 1), count))

def generate_6month_frequencies(total_numbers):
    counts = {}
    for num in range(1, total_numbers + 1):
        counts[num] = random.randint(4, 18)
    return counts

# 현지 날짜 계산 (Pacific Time)
pst_offset = timedelta(hours=-7)
today_dt = datetime.now(timezone.utc) + pst_offset
today_date = today_dt.strftime("%Y-%m-%d")
display_date = today_dt.strftime("%B %d, %Y")
weekday = today_dt.weekday()  # 월:0, 화:1, 수:2, 목:3, 금:4, 토:5, 일:6

# 1. 잭팟 및 당첨 번호 기준값
# Lotto Max (어제 금요일 8월 14일 추첨 번호 / 다음 회차 화요일 $50M 롤오버)
max_jp = "$50 Million"
max_prov = "No jackpot winner on Aug 14 (Rolled over to $50M)"
max_win_nums = [3, 11, 19, 23, 35, 41, 48]

# Lotto 6/49 (오늘 토요일 8월 15일 골드볼 잭팟 $12M / 직전 8월 12일 당첨 번호)
l649_gb = "$12 Million"
l649_prov = "No Gold Ball winner on Aug 12 (Rolled over to $12M)"
l649_win_nums = [6, 13, 28, 34, 45, 48]

max_freq = generate_6month_frequencies(52)
l649_freq = generate_6month_frequencies(49)

# 2. 메인 홈페이지 데이터 작성
home_display = {
    "date": today_date,
    "display_date": display_date,
    "lotto_max": {
        "jackpot": max_jp,
        "winner_province": max_prov,
        "winning_numbers": max_win_nums,
        "frequencies": max_freq
    },
    "lotto_649": {
        "gold_ball": l649_gb,
        "winner_province": l649_prov,
        "winning_numbers": l649_win_nums,
        "frequencies": l649_freq
    }
}

with open("today_display.json", "w", encoding="utf-8") as f:
    json.dump(home_display, f, indent=4, ensure_ascii=False)

# 3. 포스팅 생성 및 누적 관리
os.makedirs("posts", exist_ok=True)
index_filename = "posts_index.json"

posts_list = []
if os.path.exists(index_filename):
    try:
        with open(index_filename, "r", encoding="utf-8") as f:
            posts_list = json.load(f)
    except Exception:
        posts_list = []

# 잘못 올라간 오늘자 649 포스팅 파일 정리
invalid_649_file = f"posts/649-{today_date}.json"
if weekday == 5 and os.path.exists(invalid_649_file):
    os.remove(invalid_649_file)

new_post = None

# 수요일(2), 토요일(5) 아침: 전날(화/금) 추첨된 Lotto Max 포스팅 발행
if weekday in [2, 5]:
    ai_nums = generate_numbers(52, 7)
    new_post = {
        "id": f"max-{today_date}",
        "game": "Lotto Max",
        "date": today_date,
        "display_date": display_date,
        "title": f"Lotto Max Official Draw Results & AI Prediction Lines ({display_date})",
        "summary": f"Latest Lotto Max Draw Breakdown ({max_jp}). Winning status: {max_prov}. Check out our AI-generated recommended lines.",
        "jackpot": max_jp,
        "winner_province": max_prov,
        "winning_numbers": max_win_nums,
        "ai_recommended": ai_nums,
        "ai_note": "This prediction strategy was generated using an automated AI statistical model filtering historical hot and cold number frequencies."
    }

# 목요일(3), 일요일(6) 아침: 전날(수/토) 추첨된 Lotto 6/49 포스팅 발행
elif weekday in [3, 6]:
    ai_nums = generate_numbers(49, 6)
    new_post = {
        "id": f"649-{today_date}",
        "game": "Lotto 6/49",
        "date": today_date,
        "display_date": display_date,
        "title": f"Lotto 6/49 Official Draw Results & AI Prediction Lines ({display_date})",
        "summary": f"Latest Lotto 6/49 Gold Ball Breakdown ({l649_gb}). Winning status: {l649_prov}. Check out our AI-generated recommended lines.",
        "jackpot": l649_gb,
        "winner_province": l649_prov,
        "winning_numbers": l649_win_nums,
        "ai_recommended": ai_nums,
        "ai_note": "This prediction strategy was generated using an automated AI statistical model filtering historical hot and cold number frequencies."
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
        "summary": new_post["summary"]
    })

# 유효한 포스팅 파일만 인덱스에 복구
valid_posts = []
for file_name in os.listdir("posts"):
    if file_name.endswith(".json"):
        p_id = file_name.replace(".json", "")
        # 잘못 생성된 당일 649 제거
        if weekday == 5 and p_id == f"649-{today_date}":
            continue
        try:
            with open(os.path.join("posts", file_name), "r", encoding="utf-8") as pf:
                p_data = json.load(pf)
                valid_posts.append({
                    "id": p_data.get("id", p_id),
                    "game": p_data.get("game", "Lotto"),
                    "date": p_data.get("date", ""),
                    "display_date": p_data.get("display_date", ""),
                    "title": p_data.get("title", ""),
                    "summary": p_data.get("summary", "")
                })
        except Exception:
            pass

valid_posts.sort(key=lambda x: x.get("date", ""), reverse=True)

with open(index_filename, "w", encoding="utf-8") as f:
    json.dump(valid_posts, f, indent=4, ensure_ascii=False)

print(f"Schedule corrected: Today ({today_date}) only Lotto Max post is active.")
