#!/usr/bin/env python3
"""
金門競爭旅宿房價爬取腳本 v4 (Playwright)
模擬真實瀏覽器，從 Agoda 金門搜尋頁取得完整房價
"""

from playwright.sync_api import sync_playwright
import json, re
from datetime import datetime, timedelta

# ── 飯店清單 ─────────────────────────────────────────────────
HOTEL_MAP = {
    "不倒翁輕旅":       "hostel",
    "八二三行館飯店":   "general",
    "金華民宿":         "suite",
    "總兵招待所":       "suite",
    "金門市區背包客棧": "hostel",
    "浯島魁星背包棧":   "hostel",
    "背包客棧497-2館":  "hostel",
    "金城艾美商務旅館": "suite",
    "金瑞旅店":         "suite",
    "浯江大飯店":       "luxury",
    "浯島文旅":         "general",
    "海福商務飯店":     "luxury",
    "IN99精品旅館":     "luxury",
}

# ── 名稱比對關鍵字 ─────────────────────────────────────────
KEYWORDS = {
    "不倒翁": "不倒翁輕旅",     "tumbler": "不倒翁輕旅",
    "823": "八二三行館飯店",    "tourist hotel": "八二三行館飯店",
    "金華": "金華民宿",
    "總兵": "總兵招待所",
    "kinmen backpacker": "金門市區背包客棧",
    "魁星": "浯島魁星背包棧",
    "497": "背包客棧497-2館",   "backpack home 497": "背包客棧497-2館",
    "艾美": "金城艾美商務旅館", "aimei": "金城艾美商務旅館",
    "金瑞": "金瑞旅店",         "quemoy": "金瑞旅店",
    "浯江": "浯江大飯店",       "river kinmen": "浯江大飯店",
    "浯島文旅": "浯島文旅",     "h34126829": "浯島文旅",
    "海福": "海福商務飯店",     "haifu": "海福商務飯店",
    "in99": "IN99精品旅館",
}

def match_hotel(name):
    s = name.lower()
    for kw, hotel in KEYWORDS.items():
        if kw.lower() in s:
            return hotel
    return None

def parse_price(text):
    """從文字中提取合理的房價"""
    nums = re.findall(r'\d[\d,]*', str(text).replace(',', ''))
    for n in nums:
        try:
            v = int(n)
            if 300 <= v <= 30000:
                return v
        except:
            pass
    return 0

def scrape(check_in, check_out):
    results = {}
    api_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox',
                  '--disable-dev-shm-usage', '--disable-gpu']
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="zh-TW",
        )
        page = ctx.new_page()

        # ── 攔截 Agoda API 回應 ──────────────────────────────
        def on_response(resp):
            try:
                if any(x in resp.url for x in
                       ['SearchResult', 'BestMatch', 'GetHotelList',
                        'propertyList', 'cronos/property']):
                    data = resp.json()
                    api_data.append(data)
            except:
                pass
        page.on("response", on_response)

        # ── 開啟金門搜尋頁 ────────────────────────────────────
        # ── 開啟金門搜尋頁 ────────────────────────────────────
        url = (f"https://www.agoda.com/zh-tw/pages/agoda/default/"
               f"DestinationSearchResult.aspx"
               f"?city=16411&checkIn={check_in}&checkOut={check_out}"
               f"&rooms=1&adults=1&children=0&priceCur=TWD&sort=1"
               f"&los=1&selectedproperty=0")

        print("  開啟 Agoda 金門搜尋頁...")

        # 設定台灣地區標頭（讓 Agoda 以為是台灣用戶）
        page.set_extra_http_headers({
            "Accept-Language": "zh-TW,zh;q=0.9",
            "X-Forwarded-For": "211.75.108.1",   # 中華電信台灣 IP
            "CF-IPCountry": "TW",
            "X-Real-IP": "211.75.108.1",
        })
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
        except:
            page.wait_for_timeout(8000)

        # 捲動頁面觸發更多載入
        for _ in range(6):
            page.evaluate("window.scrollBy(0, 600)")
            page.wait_for_timeout(800)

        # ── 方法1：從攔截的 API 取得資料 ─────────────────────
        for d in api_data:
            try:
                props = (d.get('SearchResultList') or
                         d.get('propertyResultList') or
                         d.get('hotels') or [])
                for prop in props:
                    name = (prop.get('hotelName') or
                            prop.get('PropertyName') or
                            prop.get('name') or '')
                    price = int(
                        prop.get('displayPrice') or
                        (prop.get('lowestAveragePrice') or {}).get('perRoomPerNight') or
                        prop.get('minDisplayPrice') or
                        prop.get('price') or 0
                    )
                    matched = match_hotel(name)
                    if matched and price > 0:
                        # 若已有資料，保留較低的那個
                        existing = results.get(matched, {}).get('price', 99999)
                        if price < existing:
                            results[matched] = {"price": price, "avail": True}
            except:
                pass
        print(f"  API 攔截：取得 {len(results)} 家")

        # ── 方法2：DOM 解析飯店卡片 ──────────────────────────
        if len(results) < 8:
            try:
                cards = page.query_selector_all(
                    "[data-selenium='hotel-item'], "
                    ".hotel-listItem, "
                    "[class*='PropertyCard'], "
                    "[class*='hotel-card']"
                )
                print(f"  DOM 找到 {len(cards)} 個飯店卡片")
                for card in cards:
                    try:
                        name_el = (
                            card.query_selector("[data-selenium='hotel-name']") or
                            card.query_selector("[class*='hotel-name']") or
                            card.query_selector("h3")
                        )
                        if not name_el:
                            continue
                        name = name_el.inner_text().strip()
                        matched = match_hotel(name)
                        if not matched or matched in results:
                            continue

                        # 售完判斷：移除搜尋卡片判斷（不可靠）
                        # 搜尋卡片顯示售完 ≠ 整間售完（可能只是某房型）
                        # 只要沒有價格就標為「未知」，不標為售完

                        # 取得最低價格（找所有價格元素，取最小值）
                        price_els = card.query_selector_all(
                            "[data-selenium='display-price'], "
                            "[class*='display-price'], "
                            "[class*='lowest-price'], "
                            "[class*='Price']"
                        )
                        all_prices = []
                        for pel in price_els:
                            try:
                                p = parse_price(pel.inner_text())
                                if p > 0:
                                    all_prices.append(p)
                            except:
                                pass
                        if all_prices:
                            price = min(all_prices)  # 取最低價
                            results[matched] = {"price": price, "avail": True}
                    except:
                        continue
            except Exception as e:
                print(f"  DOM 解析錯誤: {e}")

        browser.close()
    return results


def main():
    today    = datetime.now()
    ci       = today.strftime("%Y-%m-%d")
    co       = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    ts       = today.strftime("%Y/%m/%d %H:%M")

    print(f"🏨 Playwright 抓取 {ci} 金門房價...")
    try:
        results = scrape(ci, co)
    except Exception as e:
        print(f"❌ 嚴重錯誤: {e}")
        results = {}

    out = []
    for name, cat in HOTEL_MAP.items():
        r = results.get(name, {})
        out.append({
            "name":  name,
            "cat":   cat,
            "price": r.get("price", 0),
            "avail": r.get("avail", None),
            "ok":    r.get("price", 0) > 0,
            "date":  ts,
        })

    ok   = sum(1 for h in out if h["ok"])
    sold = sum(1 for h in out if h["avail"] is False)
    unk  = sum(1 for h in out if h["avail"] is None)
    print(f"\n✅ 完成：有房價 {ok} 家 ｜ 售完 {sold} 家 ｜ 未知 {unk} 家")
    for h in out:
        s = f"NT${h['price']}" if h["price"] > 0 else (
            "售完" if h["avail"] is False else "未取得")
        print(f"  {h['name']}: {s}")

    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump({"updated": ts, "checkIn": ci, "hotels": out},
                  f, ensure_ascii=False, indent=2)
    print("💾 prices.json 已儲存")


if __name__ == "__main__":
    main()
