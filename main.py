import json
import random
import urllib.request
import re
from datetime import datetime
import zoneinfo

def get_live_jackpots():
    """Lotto Max 및 Lotto 6/49 상세 잭팟 정보 수집"""
    max_url = "https://www.wclc.com/winning-numbers/lotto-max.htm"
    l649_url = "https://www.wclc.com/winning-numbers/lotto-649.htm"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    max_jackpot = "$30 Million"
    max_millions_count = 0  # 50M 초과 시 추가 추첨 개수
    
    l649_goldball = "$10 Million"
    l649_classic = "$5 Million"

    # Lotto Max 데이터 파싱
    try:
        req = urllib.request.Request(max_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            m = re.search(r'\$(\d+)\s*Million', html, re.IGNORECASE)
            if m:
                val = int(m.group(1))
                max_jackpot = f"${val} Million"
                # $50M 초과 시 Maxmillion 개수 산정 (예: 70M이면 30개)
                if val > 50:
                    max_millions_count = val - 40
    except Exception as e:
        print(f"Lotto Max fetch error: {e}")

    # Lotto 6/49 데이터 파싱
    try:
        req = urllib.request.Request(l649_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            matches = re.findall(r'\$(\d+)\s*Million', html, re.IGNORECASE)
            if matches:
                highest_val = max([int(v) for v in matches])
                l649_goldball = f"${highest_val} Million"
    except Exception as e:
        print(f"Lotto 6/49 fetch error: {e}")

    return max_jackpot, max_millions_count, l649_goldball, l649_classic

def generate_lotto_max():
    """Lotto Max: 1~52 중 7개 조합"""
    hot_pool = [3, 11, 19, 23, 35, 41, 48, 52]
    cold_pool = [2, 7, 14, 29, 38, 50, 51]
    all_numbers = list(range(1, 53))
    
    selected_hot = random.sample(hot_pool, 3)
    selected_cold = random.sample(cold_pool, 2)
    remaining = [n for n in all_numbers if n not in selected_hot and n not in selected_cold]
    selected_random = random.sample(remaining, 2)
    return sorted(selected_hot + selected_cold + selected_random)

def generate_lotto_649():
    """Lotto 6/49: 1~49 중 6개 조합 및 Extra 4자리"""
    hot_pool = [6, 12, 20, 28, 34, 44]
    cold_pool = [4, 15, 23, 31, 40, 49]
    all_numbers = list(range(1, 50))
    
    selected_hot = random.sample(hot_pool, 2)
    selected_cold = random.sample(cold_pool, 2)
    remaining = [n for n in all_numbers if n not in selected_hot and n not in selected_cold]
    selected_random = random.sample(remaining, 2)
    
    extra_digits = [random.randint(0, 9) for _ in range(4)]
    return sorted(selected_hot + selected_cold + selected_random), extra_digits

# 현지 날짜 계산 (PST)
try:
    pst_tz = zoneinfo.ZoneInfo("America/Vancouver")
    today_date = datetime.now(pst_tz).strftime("%Y-%m-%d")
except Exception:
    today_date = datetime.now().strftime("%Y-%m-%d")

max_jp, max_mil_cnt, l649_gb, l649_classic = get_live_jackpots()
max_nums = generate_lotto_max()
l649_nums, l649_extra = generate_lotto_649()

lotto_data = {
    "date": today_date,
    "title": f"Canada Official Lotto Helper Analysis ({today_date})",
    "lotto_max": {
        "jackpot": max_jp,
        "maxmillions": max_mil_cnt,
        "recommended": max_nums,
        "hot_numbers": [3, 11, 19, 23, 35, 41, 48, 52],
        "cold_numbers": [2, 7, 14, 29, 38, 50, 51]
    },
    "lotto_649": {
        "gold_ball": l649_gb,
        "classic_jackpot": l649_classic,
        "recommended": l649_nums,
        "extra_digits": l649_extra,
        "hot_numbers": [6, 12, 20, 28, 34, 44],
        "cold_numbers": [4, 15, 23, 31, 40, 49]
    }
}

with open("today_post.json", "w", encoding="utf-8") as f:
    json.dump(lotto_data, f, indent=4, ensure_ascii=False)

print(f"Updated detailed dual lotto data for {today_date} successfully.")
