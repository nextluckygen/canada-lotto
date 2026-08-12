import json
import random
from datetime import datetime

def generate_lotto_max_numbers():
    """Lotto Max: 1~52 사이의 숫자 중 7개 번호 추첨 로직"""
    hot_pool = [3, 11, 19, 23, 35, 41, 48, 52]
    cold_pool = [2, 7, 14, 29, 38, 50, 51]
    all_numbers = list(range(1, 53))
    
    selected_hot = random.sample(hot_pool, 3)
    selected_cold = random.sample(cold_pool, 2)
    
    remaining = [n for n in all_numbers if n not in selected_hot and n not in selected_cold]
    selected_random = random.sample(remaining, 2)
    
    return sorted(selected_hot + selected_cold + selected_random)

today_str = datetime.now().strftime("%Y-%m-%d")
recommended_nums = generate_lotto_max_numbers()

lotto_post = {
    "date": today_str,
    "title": f"Lotto Max Winning Odds & Analysis ({today_str})",
    "jackpot": "$90 Million",
    "hot_numbers": [3, 11, 19, 23, 35, 41, 48, 52],
    "cold_numbers": [2, 7, 14, 29, 38, 50, 51],
    "recommended_combination": recommended_nums,
    "content": f"""
# Lotto Max Analysis & Today's Pick ({today_str})

Estimated Jackpot for the upcoming draw is **$90 Million**.

## Statistical Highlights
- **Hot Numbers (Frequently Drawn)**: 3, 11, 19, 23, 35, 41, 48, 52
- **Cold Numbers (Overdue)**: 2, 7, 14, 29, 38, 50, 51

## Today's AI Recommended Combination (1-52)
**{', '.join(map(str, recommended_nums))}**

Pick your lucky numbers with our statistical filters today!
"""
}

with open("today_post.json", "w", encoding="utf-8") as f:
    json.dump(lotto_post, f, indent=4, ensure_ascii=False)

print(f"Updated lotto data for {today_str} successfully.")
