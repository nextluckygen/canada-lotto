import json
from datetime import datetime

# 1. 오늘 날짜와 로토 임시 데이터 준비
today = datetime.now().strftime("%Y-%m-%d")

lotto_data = {
    "date": today,
    "title": f"Lotto Max Jackpot Analysis ({today})",
    "jackpot": "$70 Million",
    "hot_numbers": [11, 23, 35, 42],
    "cold_numbers": [2, 14, 49]
}

# 2. 오늘 글 내용을 텍스트로 만들기
post_text = f"""
# {lotto_data['title']}

- Estimated Jackpot: {lotto_data['jackpot']}
- Hot Numbers: {lotto_data['hot_numbers']}
- Cold Numbers: {lotto_data['cold_numbers']}

Generate your numbers today!
"""

# 3. 데이터 파일(json)로 저장하기
with open("today_post.json", "w", encoding="utf-8") as file:
    json.dump({"title": lotto_data["title"], "content": post_text}, file, indent=4)

print("오늘의 로토 포스팅 데이터 생성 완료!")
