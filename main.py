import json
import random
import urllib.request
import re
from datetime import datetime
import zoneinfo

def get_live_jackpots():
    """Lotto Max 및 Lotto 6/49 정확한 잭팟 수집"""
    max_url = "https://www.wclc.com/winning-numbers/lotto-max.htm"
    l649_url = "https://www.wclc.com/winning-numbers/lotto-649.htm"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    max_jackpot = "$30 Million"
    l649_jackpot = "$10 Million"  # 수요일 6/49 Gold Ball 잭팟 기본값 보정

    # Lotto Max 잭팟 파싱
    try:
        req = urllib.request.Request(max_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            m = re.search(r'\$(\d+)\s*Million', html, re.IGNORECASE)
            if m:
                max_jackpot = f"${m.group(1)} Million"
    except Exception as e:
        print(f"Lotto Max fetch error: {e}")

    # Lotto 6/49 잭팟 파싱 (Gold Ball Jackpot 우선 파싱)
    try:
        req = urllib.request.Request(l649_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            # Gold Ball 잭팟 또는 최우선 $XX Million 탐색
            matches = re.findall(r'\$(\d+)\s*Million', html, re.IGNORECASE)
            if matches:
                # 파싱된 금액 중 가장 높은 Jackpot 금액 선택
                highest_val = max([int(val) for val in matches])
                l649_jackpot = f"${highest_val} Million Gold Ball"
    except Exception as e:
        print(f"Lotto 6/49 fetch error: {e}")

    return max_jackpot, l649_jackpot

def generate_lotto_max():
    """Lotto Max: 1~52 중 7개 추출"""
    hot_pool = [3, 11, 19, 23, 35, 41, 48, 52]
    cold_pool = [2, 7, 14, 29, 38, 50, 51]
    all_numbers = list(range(1, 53))
    
    selected_hot = random.sample(hot_pool, 3)
    selected_cold = random.sample(cold_pool, 2)
    remaining = [n for n in all_numbers if n not in selected_hot and n not in selected_cold]
    selected_random = random.sample(remaining, 2)
    return sorted(selected_hot + selected_cold + selected_random)

def generate_lotto_649():
    """Lotto 6/49: 1~49 중 6개 추출"""
    hot_pool = [6, 12, 20, 28, 34, 44]
    cold_pool = [4, 15, 23, 31, 40, 49]
    all_numbers = list(range(1, 50))
    
    selected_hot = random.sample(hot_pool, 2)
    selected_cold = random.sample(cold_pool, 2)
    remaining = [n for n in all_numbers if n not in selected_hot and n not in selected_cold]
    selected_random = random.sample(remaining, 2)
    return sorted(selected_hot + selected_cold + selected_random)

# 현지 날짜 계산
try:
    pst_tz = zoneinfo.ZoneInfo("America/Vancouver")
    today_date = datetime.now(pst_tz).strftime("%Y-%m-%d")
except Exception:
    today_date = datetime.now().strftime("%Y-%m-%d")

max_jp, l649_jp = get_live_jackpots()
max_nums = generate_lotto_max()
l649_nums = generate_lotto_649()

lotto_post = {
    "date": today_date,
    "title": f"Canada Lotto Helper Analysis & Daily AI Line ({today_date})",
    "lotto_max": {
        "jackpot": max_jp,
        "recommended": max_nums,
        "hot_numbers": [3, 11, 19, 23, 35, 41, 48, 52],
        "cold_numbers": [2, 7, 14, 29, 38, 50, 51]
    },
    "lotto_649": {
        "jackpot": l649_jp,
        "recommended": l649_nums,
        "hot_numbers": [6, 12, 20, 28, 34, 44],
        "cold_numbers": [4, 15, 23, 31, 40, 49]
    },
    "content": f"""
<div class="space-y-6">
    <!-- Lotto Max Card -->
    <div class="bg-gradient-to-r from-emerald-50 to-teal-50 border border-emerald-200 p-5 rounded-2xl shadow-sm">
        <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-black bg-emerald-600 text-white px-3 py-1 rounded-full uppercase">Lotto Max (1-52)</span>
            <span class="text-sm font-extrabold text-emerald-800">Est. Jackpot: {max_jp}</span>
        </div>
        <p class="text-sm text-slate-700 mb-2">Today's AI Recommended Line (7 Numbers):</p>
        <p class="text-lg font-black text-emerald-700">{', '.join(map(str, max_nums))}</p>
    </div>

    <!-- Lotto 6/49 Card -->
    <div class="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 p-5 rounded-2xl shadow-sm">
        <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-black bg-blue-600 text-white px-3 py-1 rounded-full uppercase">Lotto 6/49 (1-49)</span>
            <span class="text-sm font-extrabold text-blue-800">Est. Jackpot: {l649_jp}</span>
        </div>
        <p class="text-sm text-slate-700 mb-2">Today's AI Recommended Line (6 Numbers):</p>
        <p class="text-lg font-black text-blue-700">{', '.join(map(str, l649_nums))}</p>
    </div>
</div>
"""
}

with open("today_post.json", "w", encoding="utf-8") as f:
    json.dump(lotto_post, f, indent=4, ensure_ascii=False)

print(f"Updated dual lotto data for {today_date} successfully.")
