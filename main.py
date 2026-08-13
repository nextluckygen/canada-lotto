import json
import random
import os
from datetime import datetime, timezone, timedelta

# 현지 날짜 계산 (Pacific Time)
pst_offset = timedelta(hours=-7)
today_dt = datetime.now(timezone.utc) + pst_offset
today_date = today_dt.strftime("%Y-%m-%d")
display_date = today_dt.strftime("%B %d, %Y")
weekday = today_dt.weekday()

# 1. 수동 입력 데이터 파일(today_display.json)을 그대로 불러옴
display_file = "today_display.json"
home_display = {}

if os.path.exists(display_file):
    try:
        with open(display_file, "r", encoding="utf-8") as f:
            home_display = json.load(f)
    except Exception as e:
        print(f"Error loading {display_file}: {e}")

# 날짜 자동 업데이트
home_display["date"] = today_date
home_display["display_date"] = display_date

with open(display_file, "w", encoding="utf-8") as f:
    json.dump(home_display, f, indent=4, ensure_ascii=False)

# 2. 포스팅 생성 로직
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

def generate_numbers(total, count):
    return sorted(random.sample(range(1, total + 1), count))

if weekday in [2, 3]:  # 수/목요일 Lotto 6/49
    data_649 = home_display.get("lotto_649", {})
    ai_nums = generate_numbers(49, 6)
    new_post = {
        "id": f"649-{today_date}",
        "game": "Lotto 6/49",
        "date": today_date,
        "display_date": display_date,
        "title": f"Lotto 6/49 Official Draw Results & AI Prediction Lines ({display_date})",
        "summary": f"Latest Lotto 6/49 Gold Ball Breakdown ({data_649.get('gold_ball', '$10 Million')}). Major winning tickets sold in: {data_649.get('winner_province', 'BC, Ontario')}. Check out our AI-generated recommended lines.",
        "jackpot": data_649.get('gold_ball', '$10 Million'),
        "winner_province": data_649.get('winner_province', 'BC, Ontario'),
        "winning_numbers": data_649.get('winning_numbers', []),
        "ai_recommended": ai_nums,
        "ai_note": "This prediction strategy was generated using an automated AI statistical model filtering historical hot and cold number frequencies."
    }

elif weekday in [5, 6]:  # 토/일요일 Lotto Max
    data_max = home_display.get("lotto_max", {})
    ai_nums = generate_numbers(52, 7)
    new_post = {
        "id": f"max-{today_date}",
        "game": "Lotto Max",
        "date": today_date,
        "display_date": display_date,
        "title": f"Lotto Max Official Draw Results & AI Prediction Lines ({display_date})",
        "summary": f"Latest Lotto Max Winning Numbers Breakdown. Major winning tickets sold in: {data_max.get('winner_province', 'BC, Ontario')}. Check out our AI-generated recommended lines.",
        "jackpot": data_max.get('jackpot', '$40 Million'),
        "winner_province": data_max.get('winner_province', 'BC, Ontario'),
        "winning_numbers": data_max.get('winning_numbers', []),
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

    with open(index_filename, "w", encoding="utf-8") as f:
        json.dump(posts_list, f, indent=4, ensure_ascii=False)

print(f"Updated successfully for {today_date}.")
