import json
import random
import urllib.request
import re
import ssl
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
                max_prov = f"Winning Tickets Sold in: {', '.join(provinces)}"
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

pst_offset = timedelta(hours=-7)
today_date = (datetime.now(timezone.utc) + pst_offset).strftime("%Y-%m-%d")

max_jp, max_mil, l649_gb, l649_cl, max_prov, l649_prov = get_live_jackpots()

lotto_data = {
    "date": today_date,
    "title": f"Canada Official Lotto Helper Analysis ({today_date})",
    "lotto_max": {
        "jackpot": max_jp,
        "maxmillions": max_mil,
        "winner_province": max_prov,
        "recommended": generate_numbers(52, 7),
        "hot_numbers": [3, 11, 19, 23, 35, 41, 48, 52],
        "cold_numbers": [2, 7, 14, 29, 38, 50, 51]
    },
    "lotto_649": {
        "gold_ball": l649_gb,
        "classic_jackpot": l649_cl,
        "winner_province": l649_prov,
        "recommended": generate_numbers(49, 6),
        "hot_numbers": [6, 12, 20, 28, 34, 44],
        "cold_numbers": [4, 15, 23, 31, 40, 49]
    }
}

with open("today_post.json", "w", encoding="utf-8") as f:
    json.dump(lotto_data, f, indent=4, ensure_ascii=False)

print(f"Successfully generated post for {today_date}")
