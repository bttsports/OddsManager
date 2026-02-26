"""Fetch markets by series_ticker (format that returns data in browser).
   https://demo-api.kalshi.co/trade-api/v2/markets?series_ticker=KXMAINEHOUSE94SPECIAL
"""
import requests

SERIES_TICKER = "KXMAINEHOUSE94SPECIAL"
URL = f"https://demo-api.kalshi.co/trade-api/v2/markets?series_ticker={SERIES_TICKER}"

print(f"GET {URL}")
resp = requests.get(URL)
print(f"Status: {resp.status_code}")
data = resp.json()
markets = data.get("markets") or []
cursor = data.get("cursor", "")
print(f"Cursor: {cursor!r}")
print(f"Markets count: {len(markets)}")
for i, m in enumerate(markets[:5]):
    print(f"  [{i+1}] {m.get('ticker')}  {(m.get('title') or '')[:60]}...")
