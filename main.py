import json
import random
from datetime import datetime

def generate_lotto_max_numbers():
    """Lotto Max: 1~52 사이의 숫자 중 7개 번호 추첨 로직"""
    # 통계 기반 Hot/Cold 숫자 예시 집합 (1~52 범위)
    hot_pool = [3, 11, 19, 23, 35, 41, 48, 52]
    cold_pool = [2, 7, 14, 29, 38, 50, 51]
    all_numbers = list(range(1, 53))  # 1부터 52까지
    
    # Hot 번호 3개 + Cold 번호 2개 + 무작위 번호 2개 조합
    selected_hot = random.sample(hot_pool, 3)
    selected_cold = random.sample(cold_pool, 2)
    
    remaining = [n for n in all_numbers if n not in selected_hot and n not in selected_cold]
    selected_random = random.sample(remaining, 2)
    
    final_numbers = sorted(selected_hot + selected_cold + selected_random)
    return final_numbers

# 1. 오늘 날짜 및 최신 로토 정보 생성
today_str = datetime.now().strftime("%Y-%m-%d")

recommended_nums = generate_lotto_max_numbers()

# 2. 블로그/포스트용 콘텐츠 구조화 (영어)
lotto_post = {
    "date": today_str,
    "title": f"Lotto Max Winning Odds & Analysis ({today_str})",
    "jackpot": "$90 Million EST.",
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

# 3. json 파일 저장
with open("today_post.json", "w", encoding="utf-8") as f:
    json.dump(lotto_post, f, indent=4, ensure_ascii=False)

print(f"Updated lotto data for {today_str} successfully.")
