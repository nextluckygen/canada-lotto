import json
import random
import urllib.request
import re
import ssl
import os
from datetime import datetime, timezone, timedelta

def get_live_jackpots():
    max_url = "https://www.wclc.com/winning-numbers/lotto-max.htm"
    l649_url = "https://www.wclc.com/winning-numbers/lotto-649.htm"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    
    context = ssl._create_unverified_context()
    
    max_jackpot = "$40 Million"
    max_millions_count = 0
    l649_goldball = "$10 Million"
    l649_classic = "$5 Million"
    
    max_prov = "No Jackpot Winner (Rolled Over to $40M)"
    l649_prov = "Guaranteed Gold Ball Draw Active"

    # Lotto Max
    try:
        req = urllib.request.Request(max_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=context) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            matches = re.findall(r'\$\s*(\d+)\s*Million', html, re.IGNORECASE)
            if matches:
                vals = [int(v) for v in matches]
                max_val = max(vals)
                if max_val >= 10:
                    max_jackpot = f"${max_val} Million"
                    if max_val > 50:
                        max_millions_count = max_val - 40

            provinces = []
            if "Ontario" in html: provinces.append("Ontario")
            if "British Columbia" in html or "BC" in html: provinces.append("British Columbia")
            if "Western Canada" in html or "Prairie" in html or "Alberta" in html: provinces.append("Prairies / Alberta")
            if "Quebec" in html: provinces.append("Quebec")
            if "Atlantic" in html: provinces.append("Atlantic Canada")
                
            if provinces:
                max_prov = f"Major Winning Tickets Sold in: {', '.join(provinces)}"
    except Exception as e:
        print(f"Lotto Max fetch warning: {e}")

    # Lotto 6/49
    try:
        req = urllib.request.Request(l649_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=context) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            matches = re.findall(r'\$\s*(\d+)\s*Million', html, re.IGNORECASE)
            if matches:
                vals = [int(v) for v in matches]
                valid_vals = [v for v in vals if v >= 5]
                if valid_vals:
                    l649_goldball = f"${max(valid_vals)} Million"
    except Exception as e:
        print(f"Lotto 6/49 fetch warning: {e}")

    return max_jackpot, max_millions_count, l649_goldball, l649_classic, max_prov, l649_prov

def generate_numbers(total, count):
    return sorted(random.sample(range(1, total + 1), count))

# 현지 날짜 계산 (Pacific Time)
pst_offset = timedelta(hours=-7)
today_dt = datetime.now(timezone.utc) + pst_offset
today_date = today_dt.strftime("%Y-%m-%d")
display_date = today_dt.strftime("%B %d, %Y")

max_jp, max_mil, l649_gb, l649_cl, max_prov, l649_prov = get_live_jackpots()

post_content = {
    "id": today_date,
    "date": today_date,
    "display_date": display_date,
    "title": f"Canada Lotto Draw Breakdown & AI Strategy Report ({display_date})",
    "summary": f"Latest Lotto Max Jackpot est. {max_jp} & 6/49 Gold Ball {l649_gb}. Breakdown of recent winning provinces and AI recommended lines for the upcoming draws.",
    "lotto_max": {
        "jackpot": max_jp,
        "maxmillions": max_mil,
        "winner_province": max_prov,
        "recommended": generate_numbers(52, 7)
    },
    "lotto_649": {
        "gold_ball": l649_gb,
        "classic_jackpot": l649_cl,
        "winner_province": l649_prov,
        "recommended": generate_numbers(49, 6)
    }
}

# 1. posts 디렉터리 내에 개별 포스팅 JSON 저장
os.makedirs("posts", exist_ok=True)
post_filename = f"posts/{today_date}.json"
with open(post_filename, "w", encoding="utf-8") as f:
    json.dump(post_content, f, indent=4, ensure_ascii=False)

# 2. posts_index.json 업데이트 (포스팅 목록 보관)
index_filename = "posts_index.json"
posts_list = []

if os.path.exists(index_filename):
    try:
        with open(index_filename, "r", encoding="utf-8") as f:
            posts_list = json.load(f)
    except Exception:
        posts_list = []

# 중복 제거 후 최신 포스팅 맨 앞에 추가
posts_list = [p for p in posts_list if p.get("id") != today_date]
posts_list.insert(0, {
    "id": today_date,
    "date": today_date,
    "display_date": display_date,
    "title": post_content["title"],
    "summary": post_content["summary"]
})

with open(index_filename, "w", encoding="utf-8") as f:
    json.dump(posts_list, f, indent=4, ensure_ascii=False)

# 하위 호환용 today_post.json도 유지
with open("today_post.json", "w", encoding="utf-8") as f:
    json.dump(post_content, f, indent=4, ensure_ascii=False)

print(f"Successfully published blog post and updated index for {today_date}")
