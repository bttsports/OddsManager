"""
Kalshi per-stake market making bot.
Reads config from market_making/config.json (or MARKET_MAKING_CONFIG path).
Run: python -m market_making.bot
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request
from typing import Any, Optional

# Ensure project root is on path
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.chdir(_project_root)

# Load .env
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_project_root, ".env"))
except ImportError:
    pass

from betting_outs.kalshi.kalshi import get_client

DEFAULT_CONFIG_PATH = os.path.join(_script_dir, "config.json")


def load_config(path: Optional[str] = None) -> dict:
    """Load config from JSON file."""
    p = path or os.environ.get("MARKET_MAKING_CONFIG") or DEFAULT_CONFIG_PATH
    with open(p, "r") as f:
        return json.load(f)


def market_mean_cents(best_bid: int, best_ask: int) -> int:
    """Round down: (48+49)/2 = 48.5 -> 48."""
    return math.floor((best_bid + best_ask) / 2)


def repost_price_from_base(
    stake: dict,
    prev_fill: Optional[int],
    best_bid: int,
    best_ask: int,
    side: str,
) -> int:
    """Compute repost price from base, then subtract cents_off."""
    base = stake.get("repost_base") or "previous_fill"
    if base == "previous_fill" and prev_fill is not None:
        base_price = prev_fill
    elif base == "market_mean":
        base_price = market_mean_cents(best_bid, best_ask)
    elif base == "market_best_offer":
        base_price = best_ask if side == "yes" else (100 - best_bid)
    else:
        base_price = prev_fill or 50
    cents_off = max(0, int(stake.get("cents_off") or 0))
    return max(1, min(99, base_price - cents_off))


def send_alert(url: Optional[str], ticker: str, reason: str) -> None:
    """POST alert to webhook and print."""
    print(f"ALERT: {ticker} - {reason}")
    if url:
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps({"ticker": ticker, "reason": reason}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print(f"Alert webhook failed: {e}")


def get_orderbook(client: Any, ticker: str, env: str) -> tuple[int, int]:
    """Fetch orderbook and return (best_bid, best_ask). Yes at best bid, no at best ask."""
    try:
        data = client.get_orderbook(ticker)
        ob = data.get("orderbook") or {}
        yes_bids = ob.get("yes") or []
        no_bids = ob.get("no") or []
        # Yes bids: [[price, qty], ...] sorted ascending; best bid = last
        # No bid at price X = Yes ask at 100-X
        best_yes_bid = int(yes_bids[-1][0]) if yes_bids else 1
        best_no_bid = int(no_bids[-1][0]) if no_bids else 1
        best_yes_ask = 100 - best_no_bid  # No bid at 51 = Yes ask at 49
        best_no_ask = 100 - best_yes_bid
        return best_yes_bid, best_yes_ask
    except Exception as e:
        print(f"Orderbook fetch failed for {ticker}: {e}")
        return 1, 99


def run(config: dict, env: Optional[str] = None) -> None:
    """Run the market making loop."""
    env = (env or config.get("env") or "DEMO").upper()
    event_ticker = config.get("event_ticker") or ""
    check_interval = int(config.get("check_interval_sec") or 30)
    alert_url = config.get("alert_webhook_url")
    stakes = config.get("stakes") or []

    if not stakes:
        print("No stakes in config. Exiting.")
        return

    client = get_client(env)

    # Per-stake state: ticker -> {total_filled, last_fill_price, our_order_ids, paused}
    state: dict[str, dict] = {}
    our_order_ids: set[str] = set()
    processed_order_ids: set[str] = set()

    def place_initial_orders(stake: dict) -> list[str]:
        """Place initial orders for a stake. Returns list of order_ids."""
        ticker = stake.get("ticker")
        shares = int(stake.get("shares") or 0)
        side = (stake.get("side") or "yes").lower()
        yes_price = stake.get("yes_price")
        no_price = stake.get("no_price")
        if not ticker or shares < 1:
            return []
        order_ids = []
        if side in ("yes", "both") and yes_price is not None:
            try:
                r = client.create_order(
                    ticker=ticker,
                    action="buy",
                    side="yes",
                    count=shares,
                    yes_price=int(yes_price),
                    client_order_id=f"mm_{ticker}_yes",
                )
                order_ids.append(r.get("order", {}).get("order_id") or r.get("order_id", ""))
            except Exception as e:
                print(f"Place yes failed {ticker}: {e}")
        if side in ("no", "both") and no_price is not None:
            try:
                r = client.create_order(
                    ticker=ticker,
                    action="buy",
                    side="no",
                    count=shares,
                    no_price=int(no_price),
                    client_order_id=f"mm_{ticker}_no",
                )
                order_ids.append(r.get("order", {}).get("order_id") or r.get("order_id", ""))
            except Exception as e:
                print(f"Place no failed {ticker}: {e}")
        return [oid for oid in order_ids if oid]

    def process_fill(stake: dict, order: dict) -> None:
        """Handle a filled order: repost if within limits."""
        ticker = stake.get("ticker")
        if not ticker or state.get(ticker, {}).get("paused"):
            return
        s = state[ticker]
        filled_count = int(order.get("count") or order.get("remaining_count") or 0)
        if filled_count <= 0:
            filled_count = int(order.get("yes_count") or order.get("no_count") or order.get("count") or 0)
        fill_price = order.get("yes_price") or order.get("no_price")
        if fill_price is not None:
            s["last_fill_price"] = int(fill_price)
        s["total_filled"] = s.get("total_filled", 0) + filled_count
        max_shares = stake.get("max_shares")
        if max_shares is not None and s["total_filled"] >= int(max_shares):
            send_alert(alert_url, ticker, f"max_shares reached ({s['total_filled']})")
            s["paused"] = True
            return
        pct = int(stake.get("pct_reload") or 100)
        original = int(stake.get("shares") or 1)
        repost_size = max(1, int(original * pct / 100))
        if max_shares is not None:
            remaining = int(max_shares) - s["total_filled"]
            if repost_size > remaining:
                send_alert(alert_url, ticker, f"repost would exceed max_shares (filled={s['total_filled']})")
                s["paused"] = True
                return
        best_bid, best_ask = get_orderbook(client, ticker, env)
        filled_side = (order.get("side") or "yes").lower()
        stake_side = (stake.get("side") or "yes").lower()
        new_price = repost_price_from_base(
            stake, s.get("last_fill_price"), best_bid, best_ask, filled_side
        )
        try:
            if filled_side == "yes" and stake_side in ("yes", "both"):
                r = client.create_order(
                    ticker=ticker,
                    action="buy",
                    side="yes",
                    count=repost_size,
                    yes_price=new_price,
                    client_order_id=f"mm_{ticker}_yes",
                )
                nid = r.get("order", {}).get("order_id") or r.get("order_id")
                if nid:
                    our_order_ids.add(str(nid))
                print(f"Reposted {ticker} YES {repost_size} @ {new_price}c")
            if filled_side == "no" and stake_side in ("no", "both"):
                r = client.create_order(
                    ticker=ticker,
                    action="buy",
                    side="no",
                    count=repost_size,
                    no_price=new_price,
                    client_order_id=f"mm_{ticker}_no",
                )
                nid = r.get("order", {}).get("order_id") or r.get("order_id")
                if nid:
                    our_order_ids.add(str(nid))
                print(f"Reposted {ticker} NO {repost_size} @ {new_price}c")
        except Exception as e:
            print(f"Repost failed {ticker}: {e}")
            send_alert(alert_url, ticker, f"repost failed: {e}")

    # Initialize state and place initial orders
    for stake in stakes:
        ticker = stake.get("ticker")
        if not ticker:
            continue
        state[ticker] = {
            "total_filled": 0,
            "last_fill_price": None,
            "active_order_ids": [],
            "paused": False,
        }
        ids = place_initial_orders(stake)
        state[ticker]["our_order_ids"] = ids
        our_order_ids.update(ids)
        if ids:
            print(f"Placed initial orders for {ticker}: {ids}")

    print(f"Market making started for {event_ticker}. Check interval: {check_interval}s")

    while True:
        try:
            resp = client.get_orders(limit=100, status="executed")
            orders = resp.get("orders") or []
            for o in orders:
                oid = str(o.get("order_id") or o.get("id") or "")
                if not oid or oid in processed_order_ids or oid not in our_order_ids:
                    continue
                ticker = (o.get("ticker") or "").strip()
                for stake in stakes:
                    if (stake.get("ticker") or "").strip() == ticker:
                        processed_order_ids.add(oid)
                        process_fill(stake, o)
                        # Repost creates new order; add to our set when we place it
                        break
        except Exception as e:
            print(f"Poll error: {e}")
        time.sleep(check_interval)


def main() -> None:
    env = os.environ.get("KALSHI_ENV", "DEMO").upper()
    config = load_config()
    run(config, env)


if __name__ == "__main__":
    main()
