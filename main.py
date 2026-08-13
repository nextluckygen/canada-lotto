import json
import random
import urllib.request
import xml.etree.ElementTree as ET
import ssl
import os
from datetime import datetime, timezone, timedelta

def get_official_lotto_data():
    # WCLC 공식 RSS 피드 주소
    rss_url = "https://www.wclc.com/rss/winning-numbers.xml"
    headers = {'User-Agent': 'Mozilla/5.0'}
    context = ssl._create_unverified_context()
    
    max_win_nums = [3, 11, 19, 23, 35, 41, 48]
    l649_win_nums = [5, 14, 22, 29, 33, 41]
    max_jp = "$40 Million"
    l649_gb = "$10 Million"

    try:
        req = urllib.request.Request(rss_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=context) as resp:
            xml_data = resp.read()
            root = ET.fromstring(xml_data)

            for item in root.findall('.//item'):
                title = item.find('title').text if item.find('title') is not None else ""
                desc = item.find('description').text if item.find('description') is not None else ""

                # Lotto Max 파싱
                if "LOTTO MAX" in title.upper():
                    # RSS description 태그에서 숫자 추출
                    nums = [int(s) for s in desc.split() if s.isdigit()]
                    if len(nums) >= 7:
                        max_win_nums = sorted(nums[:7])

                # Lotto 6/49 파싱
                if "LOTTO 6/49" in title.upper():
                    nums = [int(s) for s in desc.split() if s.isdigit()]
                    if len(nums) >= 6:
                        l649_win_nums = sorted(nums[:6])

    except Exception as e:
        print(f"RSS Parsing Error: {e}")

    return max_jp, "Ontario, Western Canada", max_win_nums, l649_gb, "Ontario, BC", l649_win_nums
