import requests
import json

API_KEY = "ysAgZSGVFoGtFzXWLA8RsmimFTvBHPkH"
BASE_URL = "https://app.ticketmaster.com/discovery/v2"


def get_events(keyword=None, city=None, country_code="US", size=10, page=0):
    """获取活动列表"""
    url = f"{BASE_URL}/events.json"
    params = {
        "apikey": API_KEY,
        "size": size,
        "page": page,
    }
    if keyword:
        params["keyword"] = keyword
    if city:
        params["city"] = city
    if country_code:
        params["countryCode"] = country_code

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    events = []
    if "_embedded" in data and "events" in data["_embedded"]:
        for e in data["_embedded"]["events"]:
            event = {
                "id": e.get("id"),
                "name": e.get("name"),
                "date": e.get("dates", {}).get("start", {}).get("localDate"),
                "time": e.get("dates", {}).get("start", {}).get("localTime"),
                "status": e.get("dates", {}).get("status", {}).get("code"),
                "url": e.get("url"),
                "venue": None,
                "city": None,
                "state": None,
                "genre": None,
                "price_min": None,
                "price_max": None,
            }
            # 场馆信息
            venues = e.get("_embedded", {}).get("venues", [])
            if venues:
                event["venue"] = venues[0].get("name")
                event["city"] = venues[0].get("city", {}).get("name")
                event["state"] = venues[0].get("state", {}).get("name")
            # 分类信息
            classifications = e.get("classifications", [])
            if classifications:
                genre = classifications[0].get("genre", {})
                event["genre"] = genre.get("name")
            # 价格
            price_ranges = e.get("priceRanges", [])
            if price_ranges:
                event["price_min"] = price_ranges[0].get("min")
                event["price_max"] = price_ranges[0].get("max")

            events.append(event)

    total = data.get("page", {}).get("totalElements", 0)
    return events, total


def get_event_detail(event_id):
    """获取单个活动详情"""
    url = f"{BASE_URL}/events/{event_id}.json"
    params = {"apikey": API_KEY}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def get_venues(keyword, country_code="US", size=5):
    """搜索场馆"""
    url = f"{BASE_URL}/venues.json"
    params = {
        "apikey": API_KEY,
        "keyword": keyword,
        "countryCode": country_code,
        "size": size,
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    venues = []
    if "_embedded" in data and "venues" in data["_embedded"]:
        for v in data["_embedded"]["venues"]:
            venues.append({
                "id": v.get("id"),
                "name": v.get("name"),
                "address": v.get("address", {}).get("line1"),
                "city": v.get("city", {}).get("name"),
                "state": v.get("state", {}).get("name"),
                "capacity": v.get("generalInfo", {}).get("generalRule"),
                "url": v.get("url"),
            })
    return venues


def get_attractions(keyword, size=5):
    """搜索艺人/吸引物"""
    url = f"{BASE_URL}/attractions.json"
    params = {
        "apikey": API_KEY,
        "keyword": keyword,
        "size": size,
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    attractions = []
    if "_embedded" in data and "attractions" in data["_embedded"]:
        for a in data["_embedded"]["attractions"]:
            attractions.append({
                "id": a.get("id"),
                "name": a.get("name"),
                "genre": a.get("classifications", [{}])[0].get("genre", {}).get("name"),
                "url": a.get("url"),
                "upcoming_events": a.get("upcomingEvents", {}).get("_total"),
            })
    return attractions


if __name__ == "__main__":
    print("=" * 60)
    print("Ticketmaster API 示例")
    print("=" * 60)

    # 1. 搜索活动
    print("\n[1] 搜索 'Taylor Swift' 活动（前5条）")
    events, total = get_events(keyword="Taylor Swift", size=5)
    print(f"共找到 {total} 个结果")
    for e in events:
        print(f"  - {e['name']} | {e['date']} | {e['venue']}, {e['city']} | ${e['price_min']} ~ ${e['price_max']}")

    # 2. 按城市搜索
    print("\n[2] 搜索洛杉矶近期活动（前5条）")
    events, total = get_events(city="Los Angeles", size=5)
    print(f"共找到 {total} 个结果")
    for e in events:
        print(f"  - {e['name']} | {e['date']} | {e['genre']} | {e['venue']}")

    # 3. 搜索场馆
    print("\n[3] 搜索 'Madison Square Garden'")
    venues = get_venues("Madison Square Garden")
    for v in venues:
        print(f"  - {v['name']} | {v['city']}, {v['state']} | {v['address']}")

    # 4. 搜索艺人
    print("\n[4] 搜索艺人 'Beyonce'")
    attractions = get_attractions("Beyonce")
    for a in attractions:
        print(f"  - {a['name']} | 类型: {a['genre']} | 即将演出: {a['upcoming_events']} 场")

    print("\n完成！")
