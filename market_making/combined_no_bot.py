"""
Combined No Spread bot for Kalshi.
Offers No liquidity on all stakes when combined best No ask < max_combined.
Cancels all orders immediately when condition fails.
Run: python -m market_making.combined_no_bot
"""
from __future__ import annotations

import json
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

DEFAULT_CONFIG_PATH = os.path.join(_script_dir, "combined_no_config.json")


def load_config(path: Optional[str] = None) -> dict:
    """Load config from JSON file."""
    p = path or os.environ.get("COMBINED_NO_CONFIG") or DEFAULT_CONFIG_PATH
    with open(p, "r") as f:
        return json.load(f)


def send_alert(url: Optional[str], reason: str, details: Optional[dict] = None) -> None:
    """POST alert to webhook and print."""
    print(f"ALERT: {reason}")
    if url:
        try:
            payload = {"reason": reason}
            if details:
                payload.update(details)
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print(f"Alert webhook failed: {e}")


def get_best_no_ask(client: Any, ticker: str) -> Optional[int]:
    """
    Fetch orderbook and return best No ask (price at which we'd sell No).
    best_no_ask = 100 - best_yes_bid. Returns None if orderbook empty/failed.
    """
    try:
        data = client.get_orderbook(ticker)
        ob = data.get("orderbook") or {}
        yes_bids = ob.get("yes") or []
        if not yes_bids:
            return None
        best_yes_bid = int(yes_bids[-1][0])
        best_no_ask = 100 - best_yes_bid
        return max(1, min(99, best_no_ask))
    except Exception as e:
        print(f"Orderbook fetch failed for {ticker}: {e}")
        return None


def run(config: dict, env: Optional[str] = None) -> None:
    """Run the combined No spread loop."""
    env = (env or config.get("env") or "DEMO").upper()
    tickers = config.get("tickers") or []
    max_combined = int(config.get("max_combined") or 99)
    shares = int(config.get("shares") or 10)
    check_interval = int(config.get("check_interval_sec") or 5)
    alert_url = config.get("alert_webhook_url")

    if not tickers:
        print("No tickers in config. Exiting.")
        return

    if shares < 1:
        print("Shares must be >= 1. Exiting.")
        return

    client = get_client(env)
    our_order_ids: set[str] = set()
    orders_up = False

    while True:
        try:
            # Fetch orderbooks for all tickers
            best_no_asks: dict[str, int] = {}
            for ticker in tickers:
                ask = get_best_no_ask(client, ticker)
                if ask is not None:
                    best_no_asks[ticker] = ask
                else:
                    best_no_asks[ticker] = 99  # Conservative: treat as expensive

            combined = sum(best_no_asks.values())

            if combined >= max_combined:
                # Condition failed: cancel all orders
                if our_order_ids:
                    for oid in list(our_order_ids):
                        try:
                            client.cancel_order(oid)
                            our_order_ids.discard(oid)
                        except Exception as e:
                            print(f"Cancel failed {oid}: {e}")
                    print(f"Condition failed (combined={combined} >= {max_combined}). Cancelled all orders.")
                    if alert_url:
                        send_alert(
                            alert_url,
                            f"combined_no_condition_failed",
                            {"combined": combined, "max_combined": max_combined},
                        )
                orders_up = False
            else:
                # Condition passes: place orders if we don't have them up
                if not orders_up:
                    for ticker, no_price in best_no_asks.items():
                        try:
                            r = client.create_order(
                                ticker=ticker,
                                action="sell",
                                side="no",
                                count=shares,
                                no_price=no_price,
                                client_order_id=f"combined_no_{ticker}",
                            )
                            oid = r.get("order", {}).get("order_id") or r.get("order_id")
                            if oid:
                                our_order_ids.add(str(oid))
                            print(f"Placed sell No {ticker} @ {no_price}c x{shares} (combined={combined})")
                        except Exception as e:
                            print(f"Place sell No failed {ticker}: {e}")
                    orders_up = True

        except Exception as e:
            print(f"Loop error: {e}")
            if alert_url:
                send_alert(alert_url, "combined_no_loop_error", {"error": str(e)})

        time.sleep(check_interval)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="Path to config JSON")
    args = parser.parse_args()
    config = load_config(args.config) if args.config else load_config()
    run(config)
