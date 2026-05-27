#!/usr/bin/env python3
"""
金門競爭旅宿房價自動爬取腳本 v2
透過 Agoda 搜尋 API 取得金門地區所有旅宿今日房價
"""

import requests
import json
import re
import time
from datetime import datetime, timedelta
import random

# ── 目標飯店名稱對照表 ─────────────────────────────────────────
HOTEL_MAP = {
    "不倒翁輕旅":       {"cat": "hostel",  "id": None},
    "八二三行館飯店":   {"cat": "general", "id": None},
    "金華民宿":         {"cat": "suite",   "id": None},
    "總兵招待所":       {"cat": "suite",   "id": None},
    "金門市區背包客棧": {"cat": "hostel",  "id": None},
    "浯島魁星背包棧":   {"cat": "hostel",  "id": None},
    "背包客棧497-2館":  {"cat": "hostel",  "id": None},
    "金城艾美商務旅館": {"cat": "suite",   "id": None},
    "金瑞旅店":         {"cat": "suite",   "id": None},
    "浯江大飯店":       {"cat": "luxury",  "id": None},
    "浯島文旅":         {"cat": "general", "id": None},
    "海福商務飯店":     {"cat": "luxury",  "id": None},
    "IN99精品旅館":     {"cat": "luxury",  "id": None},
}

# 名稱關鍵字比對（處理中英文差異）
NAME_KEYWORDS = {
    "不倒翁":   "不倒翁輕旅",
    "tumbler":  "不倒翁輕旅",
    "823":      "八二三行館飯店",
    "tourist hotel": "八二三行館飯店",
    "金華":     "金華民宿",
    "總兵":     "總兵招待所",
    "kinmen backpacker": "金門市區背包客棧",
    "魁星":     "浯島魁星背包棧",
    "497":      "背包客棧497-2館",
    "backpack home 497": "背包客棧497-2館",
    "艾美":     "金城艾美商務旅館",
    "aimei":    "金城艾美商務旅館",
    "金瑞":     "金瑞旅店",
    "quemoy":   "金瑞旅店",
    "浯江":     "浯江大飯店",
    "river kinmen": "浯江大飯店",
    "浯島文旅": "浯島文旅",
    "h34126829": "浯島文旅",
    "海福":     "海福商務飯店",
    "haifu":    "海福商務飯店",
    "in99":     "IN99精品旅館",
}

def match_hotel_name(name_str):
    """根據關鍵字比對飯店名稱"""
    s = name_str.lower()
    for kw, hotel in NAME_KEYWORDS.items():
        if kw.lower() in s:
            return hotel
    return None


def fetch_agoda_search(check_in, check_out):
    """
    呼叫 Agoda 搜尋 API 取得金門地區旅宿房價
    city_id = 16411 (金門)
    """
    results = {}

    # 方法一：Agoda property search API
    try:
        url = "https://www.agoda.com/api/cronos/property/BestMatch/GetSearchResultList"
        params = {
            "finalPriceView": "1",
            "isShowMobileNotice": "false",
            "checkIn": check_in,
            "checkOut": check_out,
            "cityId": "16411",      # 金門縣
            "rooms": "1",
            "adults": "2",
            "children": "0",
            "priceCur": "TWD",
            "los": "1",
            "cid": "1844104",
            "currency": "TWD",
            "pageTypeId": "1",
            "culture": "zh-TW",
            "userId": "0",
            "userCurrency": "TWD",
            "countryCode": "TW",
            "isPriceLoaded": "false",
            "priceTypeCode": "All",
            "isIncludeInternalSortRankProperties": "true",
            "sortField": "1",
            "sortOrder": "1",
            "isFreeBreakfast": "false",
            "isSafetyFirst": "false",
            "isNhaSanPham": "false",
            "isShowUnAvailable": "false",
            "searchGuid": "none",
            "searchBoardTypeId": "0",
            "travellerType": "2",
            "numOfHotel": "50",
            "pageIndex": "0",
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-TW,zh;q=0.9",
            "Referer": "https://www.agoda.com/zh-tw/",
            "X-Requested-With": "XMLHttpRequest",
        }
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            properties = data.get("SearchResultList", []) or data.get("propertyResultList", [])
            for p in properties:
                name = p.get("hotelName","") or p.get("PropertyName","")
                price = (p.get("displayPrice",0) or
                         p.get("LowestAveragePrice",{}).get("perRoomPerNight",0) or 0)
                avail = price > 0
                matched = match_hotel_name(name)
                if matched and int(price) > 0:
                    results[matched] = {"price": int(price), "avail": avail, "source": "api"}
            print(f"  API 方法一取得 {len(results)} 家")
    except Exception as e:
        print(f"  API 方法一失敗: {e}")

    return results


def fetch_individual_pages(hotels_needed, check_in, check_out):
    """針對未取得的飯店，直接訪問頁面"""
    HOTEL_URLS = {
        "不倒翁輕旅":       "https://www.agoda.com/zh-tw/tumbler-travel/hotel/all/kinmen-islands-tw.html",
        "八二三行館飯店":   "https://www.agoda.com/zh-tw/823-tourist-hotel/hotel/kinmen-tw.html",
        "金華民宿":         "https://www.agoda.com/zh-tw/h63113258/hotel/kinmen-islands-tw.html",
        "總兵招待所":       "https://www.agoda.com/zh-tw/h76106414/hotel/kinmen-islands-tw.html",
        "金門市區背包客棧": "https://www.agoda.com/zh-tw/kinmen-backpacker_2/hotel/kinmen-tw.html",
        "浯島魁星背包棧":   "https://www.agoda.com/zh-tw/h76945502/hotel/kinmen-islands-tw.html",
        "背包客棧497-2館":  "https://www.agoda.com/zh-tw/backpack-home-497-no-2/hotel/kinmen-tw.html",
        "金城艾美商務旅館": "https://www.agoda.com/zh-tw/aimei-hotel/hotel/kinmen-tw.html",
        "金瑞旅店":         "https://www.agoda.com/zh-tw/quemoy-hotel/hotel/kinmen-tw.html",
        "浯江大飯店":       "https://www.agoda.com/zh-tw/hotel-river-kinmen/hotel/kinmen-tw.html",
        "浯島文旅":         "https://www.agoda.com/zh-tw/h34126829/hotel/kinmen-tw.html",
        "海福商務飯店":     "https://www.agoda.com/zh-tw/haifu-hotel-suites/hotel/kinmen-tw.html",
        "IN99精品旅館":     "https://www.agoda.com/zh-tw/in99-hotel/hotel/kinmen-tw.html",
    }

    results = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9",
    }

    for name in hotels_needed:
        url = HOTEL_URLS.get(name)
        if not url:
            continue
        full_url = f"{url}?checkIn={check_in}&checkOut={check_out}&rooms=1&adults=2"
        try:
            resp = requests.get(full_url, headers=headers, timeout=15)
            html = resp.text

            # 已售完判斷
            if any(k in html for k in ["沒有空房", "no rooms", "unavailable", "soldOut\":true"]):
                results[name] = {"price": 0, "avail": False, "source": "page"}
                print(f"  {name}: 售完")
                continue

            # 找價格
            patterns = [
                r'"DiscountedPrice"[^}]*?"value"\s*:\s*(\d+)',
                r'"displayPrice"\s*:\s*(\d+)',
                r'"PriceFor1Night"\s*:\s*(\d+)',
                r'(?:price-content|hotel-price)[^>]*>\s*[\$\s]*([\d,]+)',
            ]
            found_price = None
            for pat in patterns:
                m = re.search(pat, html)
                if m:
                    p = int(str(m.group(1)).replace(',',''))
                    if 200 <= p <= 30000:
                        found_price = p
                        break

            if found_price:
                results[name] = {"price": found_price, "avail": True, "source": "page"}
                print(f"  {name}: NT${found_price}")
            else:
                print(f"  {name}: 無法解析")

            time.sleep(random.uniform(1.5, 3.0))

        except Exception as e:
            print(f"  {name}: 錯誤 {e}")

    return results


def main():
    today = datetime.now()
    check_in  = today.strftime("%Y-%m-%d")
    check_out = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    fetch_date = today.strftime("%Y/%m/%d %H:%M")

    print(f"🏨 開始抓取 {check_in} 金門地區房價...")

    # 方法一：Agoda 搜尋 API
    all_results = fetch_agoda_search(check_in, check_out)

    # 方法二：補齊未取得的飯店
    missing = [name for name in HOTEL_MAP if name not in all_results]
    if missing:
        print(f"  補充抓取 {len(missing)} 家...")
        page_results = fetch_individual_pages(missing, check_in, check_out)
        all_results.update(page_results)

    # 組合最終結果
    hotels_output = []
    for name, info in HOTEL_MAP.items():
        r = all_results.get(name, {})
        hotels_output.append({
            "name":  name,
            "cat":   info["cat"],
            "price": r.get("price", 0),
            "avail": r.get("avail", None),   # None = 未知，不是售完
            "ok":    name in all_results,
            "date":  fetch_date,
        })

    ok = sum(1 for h in hotels_output if h["ok"])
    print(f"\n✅ 完成！成功取得 {ok}/{len(hotels_output)} 家房價")
    for h in hotels_output:
        status = f"NT${h['price']}" if h['price'] else ("售完" if h['avail'] is False else "未取得")
        print(f"  {h['name']}: {status}")

    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump({
            "updated": fetch_date,
            "checkIn": check_in,
            "hotels": hotels_output
        }, f, ensure_ascii=False, indent=2)

    print("💾 已儲存至 prices.json")


if __name__ == "__main__":
    main()
