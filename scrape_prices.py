#!/usr/bin/env python3
"""
金門競爭旅宿房價自動爬取腳本
每日透過 GitHub Actions 執行，結果存入 prices.json
"""

import requests
import json
import re
import time
from datetime import datetime, timedelta
import random

# ── 14家競爭對手 ──────────────────────────────────────────────
HOTELS = [
    {"name": "不倒翁輕旅",       "cat": "hostel",  "url": "https://www.agoda.com/zh-tw/tumbler-travel/hotel/all/kinmen-islands-tw.html"},
    {"name": "八二三行館飯店",   "cat": "general", "url": "https://www.agoda.com/zh-tw/823-tourist-hotel/hotel/kinmen-tw.html"},
    {"name": "金華民宿",         "cat": "suite",   "url": "https://www.agoda.com/zh-tw/h63113258/hotel/kinmen-islands-tw.html"},
    {"name": "總兵招待所",       "cat": "suite",   "url": "https://www.agoda.com/zh-tw/h76106414/hotel/kinmen-islands-tw.html"},
    {"name": "金門市區背包客棧", "cat": "hostel",  "url": "https://www.agoda.com/zh-tw/kinmen-backpacker_2/hotel/kinmen-tw.html"},
    {"name": "浯島魁星背包棧",   "cat": "hostel",  "url": "https://www.agoda.com/zh-tw/h76945502/hotel/kinmen-islands-tw.html"},
    {"name": "背包客棧497-2館",  "cat": "hostel",  "url": "https://www.agoda.com/zh-tw/backpack-home-497-no-2/hotel/kinmen-tw.html"},
    {"name": "金城艾美商務旅館", "cat": "suite",   "url": "https://www.agoda.com/zh-tw/aimei-hotel/hotel/kinmen-tw.html"},
    {"name": "金瑞旅店",         "cat": "suite",   "url": "https://www.agoda.com/zh-tw/quemoy-hotel/hotel/kinmen-tw.html"},
    {"name": "浯江大飯店",       "cat": "luxury",  "url": "https://www.agoda.com/zh-tw/hotel-river-kinmen/hotel/kinmen-tw.html"},
    {"name": "浯島文旅",         "cat": "general", "url": "https://www.agoda.com/zh-tw/h34126829/hotel/kinmen-tw.html"},
    {"name": "海福商務飯店",     "cat": "luxury",  "url": "https://www.agoda.com/zh-tw/haifu-hotel-suites/hotel/kinmen-tw.html"},
    {"name": "IN99精品旅館",     "cat": "luxury",  "url": "https://www.agoda.com/zh-tw/in99-hotel/hotel/kinmen-tw.html"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
}

def get_price(hotel, check_in, check_out):
    """嘗試從 Agoda 頁面取得最低房價"""
    url = f"{hotel['url']}?checkIn={check_in}&checkOut={check_out}&rooms=1&adults=2&children=0&los=1"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        html = resp.text

        # 方法1：找 JSON 中的最低房價
        patterns = [
            r'"lowestAveragePrice"\s*:\s*\{[^}]*"perRoomPerNight"\s*:\s*(\d+)',
            r'"displayPrice"\s*:\s*(\d+\.?\d*)',
            r'"CrossedOutPrice"\s*:\s*\{[^}]*"value"\s*:\s*(\d+)',
            r'data-price=["\'](\d+)["\']',
            r'"price"\s*:\s*(\d+)',
        ]
        for pat in patterns:
            m = re.search(pat, html)
            if m:
                price = int(float(m.group(1)))
                if 100 <= price <= 50000:  # 合理範圍
                    avail = True
                    return price, avail

        # 方法2：判斷是否售完
        sold_out_keywords = ['sold out', 'soldout', '已售完', '無空房', 'unavailable']
        if any(k in html.lower() for k in sold_out_keywords):
            return 0, False

        # 方法3：找任何看起來像價格的數字
        prices = re.findall(r'(?:TWD|NT\$|NTD)[\s]*(\d{3,5})', html)
        if prices:
            valid = [int(p) for p in prices if 200 <= int(p) <= 20000]
            if valid:
                return min(valid), True

        return None, None  # 無法解析

    except Exception as e:
        print(f"  ✗ {hotel['name']}: {e}")
        return None, None


def main():
    today = datetime.now()
    check_in  = today.strftime("%Y-%m-%d")
    check_out = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    fetch_date = today.strftime("%Y/%m/%d %H:%M")

    print(f"🏨 開始抓取 {check_in} 入住房價...")
    results = []

    for hotel in HOTELS:
        print(f"  抓取: {hotel['name']}")
        price, avail = get_price(hotel, check_in, check_out)

        # 若抓取失敗，保留上次資料（若有的話）
        entry = {
            "name":  hotel["name"],
            "cat":   hotel["cat"],
            "price": price if price is not None else 0,
            "avail": avail if avail is not None else True,
            "date":  fetch_date,
            "ok":    price is not None,
        }
        results.append(entry)

        status = f"NT${price}" if price else ("售完" if avail is False else "未取得")
        print(f"  → {status}")
        time.sleep(random.uniform(1.5, 3.0))  # 避免被封鎖

    # 統計
    ok = sum(1 for r in results if r["ok"])
    print(f"\n✅ 完成！成功取得 {ok}/{len(results)} 家房價")

    # 寫入 prices.json
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump({
            "updated": fetch_date,
            "checkIn": check_in,
            "hotels": results
        }, f, ensure_ascii=False, indent=2)

    print("💾 已儲存至 prices.json")


if __name__ == "__main__":
    main()
