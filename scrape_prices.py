#!/usr/bin/env python3
"""
金門競爭旅宿房價爬取腳本 v5
直接訪問各飯店 Agoda 頁面，抓取右上角顯示的起始房價
背包客棧用 1 人，其餘用 2 人
"""

from playwright.sync_api import sync_playwright
import json, re
from datetime import datetime, timedelta
import time, random

# ── 飯店清單（已移除金城艾美商務旅館）───────────────────────
HOTELS = [
    {"name": "不倒翁輕旅",       "cat": "hostel",  "adults": 1,
     "url": "https://www.agoda.com/zh-tw/tumbler-travel/hotel/all/kinmen-islands-tw.html"},
    {"name": "八二三行館飯店",   "cat": "general", "adults": 2,
     "url": "https://www.agoda.com/zh-tw/823-tourist-hotel/hotel/kinmen-tw.html"},
    {"name": "金華民宿",         "cat": "suite",   "adults": 2,
     "url": "https://www.agoda.com/zh-tw/h63113258/hotel/kinmen-islands-tw.html"},
    {"name": "總兵招待所",       "cat": "suite",   "adults": 2,
     "url": "https://www.agoda.com/zh-tw/h76106414/hotel/kinmen-islands-tw.html"},
    {"name": "金門市區背包客棧", "cat": "hostel",  "adults": 1,
     "url": "https://www.agoda.com/zh-tw/kinmen-backpacker_2/hotel/kinmen-tw.html"},
    {"name": "浯島魁星背包棧",   "cat": "hostel",  "adults": 1,
     "url": "https://www.agoda.com/zh-tw/h76945502/hotel/kinmen-islands-tw.html"},
    {"name": "背包客棧497-2館",  "cat": "hostel",  "adults": 1,
     "url": "https://www.agoda.com/zh-tw/backpack-home-497-no-2/hotel/kinmen-tw.html"},
    {"name": "金瑞旅店",         "cat": "suite",   "adults": 2,
     "url": "https://www.agoda.com/zh-tw/quemoy-hotel/hotel/kinmen-tw.html"},
    {"name": "浯江大飯店",       "cat": "luxury",  "adults": 2,
     "url": "https://www.agoda.com/zh-tw/hotel-river-kinmen/hotel/kinmen-tw.html"},
    {"name": "浯島文旅",         "cat": "general", "adults": 2,
     "url": "https://www.agoda.com/zh-tw/h34126829/hotel/kinmen-tw.html"},
    {"name": "海福商務飯店",     "cat": "luxury",  "adults": 2,
     "url": "https://www.agoda.com/zh-tw/haifu-hotel-suites/hotel/kinmen-tw.html"},
    {"name": "IN99精品旅館",     "cat": "luxury",  "adults": 2,
     "url": "https://www.agoda.com/zh-tw/in99-hotel/hotel/kinmen-tw.html"},
]


def parse_price(text):
    """從文字中取出合理房價"""
    s = str(text).replace(',', '').replace('NT$', '').replace('$', '')
    nums = re.findall(r'\d+', s)
    for n in nums:
        v = int(n)
        if 200 <= v <= 50000:
            return v
    return 0


def get_starting_price(page, hotel, check_in, check_out):
    """
    訪問飯店個別頁面，抓取右上角「自 NT$ XXX」的起始價格
    """
    adults = hotel["adults"]
    url = (f"{hotel['url']}?checkIn={check_in}&checkOut={check_out}"
           f"&rooms=1&adults={adults}&children=0&los=1")

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)

        # ── 找右上角的起始價格 ────────────────────────────────
        # Agoda 飯店頁右上角通常是 "自 NT$ 972" 格式
        price_selectors = [
            "[data-selenium='PriceSection']",
            "[class*='sc-'][class*='price']",
            "[class*='startingPrice']",
            "[class*='PropertyPage'] [class*='price']",
            "span[class*='price']",
            "[class*='PriceDisplay']",
            "[class*='lowest-price']",
        ]

        for sel in price_selectors:
            try:
                els = page.query_selector_all(sel)
                for el in els:
                    txt = el.inner_text()
                    if re.search(r'\d{3,5}', txt):
                        p = parse_price(txt)
                        if p > 0:
                            return p, True
            except:
                pass

        # 備援：用正規表達式找頁面中「自 NT$」後面的數字
        try:
            content = page.inner_text("body")

            # 找 "自 NT$ 972" 這種格式
            m = re.search(r'自\s*NT\$\s*([\d,]+)', content)
            if m:
                p = parse_price(m.group(1))
                if p > 0:
                    return p, True

            # 找 "自 $972" 格式
            m = re.search(r'自\s*\$\s*([\d,]+)', content)
            if m:
                p = parse_price(m.group(1))
                if p > 0:
                    return p, True

            # 判斷是否全部售完
            sold_out_msgs = [
                "此住宿在您選擇的日期已全部售出",
                "此日期所有房型均已售完",
                "No rooms available",
            ]
            for msg in sold_out_msgs:
                if msg in content:
                    return 0, False

        except:
            pass

        return None, None

    except Exception as e:
        print(f"    連線失敗: {e}")
        return None, None


def main():
    today     = datetime.now()
    check_in  = today.strftime("%Y-%m-%d")
    check_out = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    ts        = today.strftime("%Y/%m/%d %H:%M")

    print(f"🏨 Playwright 抓取 {check_in} 金門房價（逐頁訪問）...")

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage", "--disable-gpu"]
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            extra_http_headers={
                "Accept-Language": "zh-TW,zh;q=0.9",
                "X-Forwarded-For": "211.75.108.1",
                "CF-IPCountry": "TW",
            },
        )
        page = ctx.new_page()

        for hotel in HOTELS:
            print(f"  抓取: {hotel['name']} ({hotel['adults']}人)...")
            price, avail = get_starting_price(page, hotel, check_in, check_out)

            if price and price > 0:
                status = f"NT${price:,}"
            elif avail is False:
                status = "售完"
            else:
                status = "未取得"
            print(f"    → {status}")

            results.append({
                "name":  hotel["name"],
                "cat":   hotel["cat"],
                "price": price if price else 0,
                "avail": avail,
                "ok":    bool(price and price > 0),
                "date":  ts,
            })

            time.sleep(random.uniform(2.0, 4.0))

        browser.close()

    ok   = sum(1 for r in results if r["ok"])
    sold = sum(1 for r in results if r["avail"] is False)
    unk  = sum(1 for r in results if r["avail"] is None)
    print(f"\n✅ 完成：有房價 {ok} 家 ｜ 售完 {sold} 家 ｜ 未取得 {unk} 家")

    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump({
            "updated": ts,
            "checkIn": check_in,
            "hotels":  results,
        }, f, ensure_ascii=False, indent=2)

    print("💾 prices.json 已儲存")


if __name__ == "__main__":
    main()
