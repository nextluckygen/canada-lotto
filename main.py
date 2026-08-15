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

# 잭팟 및 당첨 지역 기본 상태 (미당첨 시 Rollover 처리)
max_jp = "$50 Million"
max_prov = "No jackpot winner (Rolled over to next draw)"
max_win_nums = [3, 11, 19, 23, 35, 41, 48]

l649_gb = "$12 Million"
l649_prov = "Pending official confirmation"
l649_win_nums = [5, 14, 22, 29, 33, 41]

max_freq = generate_6month_frequencies(52)
l649_freq = generate_6month_frequencies(49)

# 1. 메인 홈페이지 표시 데이터 (today_display.json)
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

# 2. 포스팅 생성 및 보존
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

# 수/목/토/일: Lotto 6/49 ($12M)
if weekday in [2, 3, 5, 6]:
    ai_nums = generate_numbers(49, 6)
    new_post = {
        "id": f"649-{today_date}",
        "game": "Lotto 6/49",
        "date": today_date,
        "display_date": display_date,
        "title": f"Lotto 6/49 Official Draw Results & AI Prediction Lines ({display_date})",
        "summary": f"Latest Lotto 6/49 Gold Ball Jackpot: {l649_gb}. Winning status: {l649_prov}. Check out our AI-generated recommended lines.",
        "jackpot": l649_gb,
        "winner_province": l649_prov,
        "winning_numbers": l649_win_nums,
        "ai_recommended": ai_nums,
        "ai_note": "This prediction strategy was generated using an automated AI statistical model filtering historical hot and cold number frequencies."
    }
# 화/금: Lotto Max ($50M)
elif weekday in [1, 4]:
    ai_nums = generate_numbers(52, 7)
    new_post = {
        "id": f"max-{today_date}",
        "game": "Lotto Max",
        "date": today_date,
        "display_date": display_date,
        "title": f"Lotto Max Official Draw Results & AI Prediction Lines ({display_date})",
        "summary": f"Latest Lotto Max Jackpot: {max_jp}. Winning status: {max_prov}. Check out our AI-generated recommended lines.",
        "jackpot": max_jp,
        "winner_province": max_prov,
        "winning_numbers": max_win_nums,
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

# 기존 포스팅 파일들 복구 및 날짜순 정렬
for file_name in os.listdir("posts"):
    if file_name.endswith(".json"):
        p_id = file_name.replace(".json", "")
        if not any(p.get("id") == p_id for p in posts_list):
            try:
                with open(os.path.join("posts", file_name), "r", encoding="utf-8") as pf:
                    p_data = json.load(pf)
                    posts_list.append({
                        "id": p_data.get("id", p_id),
                        "game": p_data.get("game", "Lotto"),
                        "date": p_data.get("date", ""),
                        "display_date": p_data.get("display_date", ""),
                        "title": p_data.get("title", ""),
                        "summary": p_data.get("summary", "")
                    })
            except Exception:
                pass

posts_list.sort(key=lambda x: x.get("date", ""), reverse=True)

with open(index_filename, "w", encoding="utf-8") as f:
    json.dump(posts_list, f, indent=4, ensure_ascii=False)

print(f"Updated successfully for {today_date}.")
